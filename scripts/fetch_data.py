#!/usr/bin/env python3
"""Build site/data.json from the Energy-Charts v2 API (Austria).

Everything the page needs is precomputed here so the browser does no maths:
one fetch, one blob, straight to render.

Source: https://api.energy-charts.info/ (Fraunhofer ISE) — no API key.
The v2 endpoints are used throughout: they carry stable series ids, an
explicit `unit`, and the licence string, so nothing has to be guessed from
English display names or assumed about scale.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.energy-charts.info/v2"
# The daily-average series predates v2 and is served from the root path with a
# flat {days, data} body. add_season() tries v2 first and falls back to this.
API_V1 = "https://api.energy-charts.info"
COUNTRY = "at"
BZN = "AT"
OUT = Path(__file__).resolve().parent.parent / "site" / "data.json"

# How much history the page shows.
HOURS_BACK = 24
# Generation data lags roughly an hour, so over-fetch and trim to the last
# complete sample.
FETCH_DAYS = 8

# Energy-Charts series ids -> the seven groups the page draws, in the order
# they stack (bottom to top). That order is also the colour order and it is
# load-bearing: the palette was CVD-validated on exactly these adjacencies.
# Reordering the groups means re-running the validator.
GROUPS = [
    ("hydro", "Wasserkraft", "Hydro",
     ["hydro_run_of_river", "hydro_water_reservoir"]),
    ("fossil", "Fossil", "Fossil",
     ["fossil_gas", "fossil_hard_coal", "fossil_brown_coal_lignite",
      "fossil_oil", "fossil_coal_derived_gas"]),
    ("wind", "Wind", "Wind",
     ["wind_onshore", "wind_offshore"]),
    ("solar", "Photovoltaik", "Solar",
     ["solar"]),
    ("pumped", "Pumpspeicher", "Pumped storage",
     ["hydro_pumped_storage"]),
    ("biomass", "Biomasse & Abfall", "Biomass & waste",
     ["biomass", "waste"]),
    ("other", "Sonstige", "Other",
     ["geothermal", "others", "renewable_waste", "non_renewable_waste"]),
]

# Series that are not generation and must never land in a group.
NON_GENERATION = {
    "load",
    "residual_load",
    "renewable_share_of_load",
    "renewable_share_of_generation",
    "cross_border_electricity_trading",
    "hydro_pumped_storage_consumption",
}

# Everything on the page is MW. cbpf ships GW, so scale by the declared unit
# rather than trusting an endpoint to keep its current scale.
TO_MW = {"MW": 1.0, "GW": 1000.0, "KW": 0.001, "W": 1e-6}

# Austria's neighbours, mapping the cbpf series id to the country code the
# generation endpoint expects. Used to estimate what imported power was made
# of, by attributing each border flow to that country's generation mix at the
# same moment. See IMPORT_CAVEAT below — this is attribution, not tracing.
NEIGHBOURS = {
    "czech_republic": "cz",
    "germany": "de",
    "hungary": "hu",
    "italy": "it",
    "slovenia": "si",
    "switzerland": "ch",
}

# Groups for the import mix. Nuclear gets its own slot: Austria has none, so
# it never appears in the domestic chart, but it is a large share of what
# comes in. Order is the stack order and was colour-validated as such.
IMPORT_GROUPS = [
    ("hydro", "Wasserkraft", "Hydro",
     ["hydro_run_of_river", "hydro_water_reservoir", "hydro_pumped_storage"]),
    ("fossil", "Fossil", "Fossil",
     ["fossil_gas", "fossil_hard_coal", "fossil_brown_coal_lignite",
      "fossil_oil", "fossil_coal_derived_gas"]),
    ("wind", "Wind", "Wind", ["wind_onshore", "wind_offshore"]),
    ("solar", "Photovoltaik", "Solar", ["solar"]),
    ("nuclear", "Kernkraft", "Nuclear", ["nuclear"]),
    ("other", "Sonstige", "Other",
     ["biomass", "waste", "other_renewables", "geothermal", "battery", "others",
      "renewable_waste", "non_renewable_waste"]),
]

RENEWABLE_GROUPS = {"hydro", "wind", "solar"}

# Series that are consumption or derived, never generation.
NOT_GENERATION = {
    "load", "residual_load", "renewable_share_of_load",
    "renewable_share_of_generation", "cross_border_electricity_trading",
    "hydro_pumped_storage_consumption", "battery_consumption",
}


def get(path: str, base: str = API, **params) -> dict:
    """GET with backoff. The API rate-limits (429) when several countries are
    requested back to back, which this script does for the import mix."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{base}/{path}?{qs}",
                                 headers={"Accept": "application/json"})
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                payload = json.load(r)
            if payload.get("deprecated"):
                print(f"WARNING: {path} is flagged deprecated by the API", file=sys.stderr)
            return payload
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429 and e.code < 500:
                raise
        except urllib.error.URLError as e:
            last = e
        wait = 4 * (attempt + 1)
        print(f"  retry {path} ({params}) in {wait}s: {last}", file=sys.stderr)
        time.sleep(wait)
    raise last if last else RuntimeError(f"{path} failed")


def to_mw(payload: dict) -> float:
    unit = (payload.get("unit") or "MW").strip().upper()
    if unit not in TO_MW:
        raise SystemExit(f"unexpected unit {unit!r} from {payload.get('endpoint')}")
    return TO_MW[unit]


def columns(payload: dict) -> tuple[list[int], dict[str, list]]:
    """Flatten v2's row-per-timestamp shape into aligned columns."""
    rows = payload["data"]
    times = [int(datetime.fromisoformat(r["timestamp"]).timestamp()) for r in rows]
    ids = [s["id"] for s in payload["series"]]
    cols = {i: [r["values"].get(i) for r in rows] for i in ids}
    return times, cols


def clean(vals: list | None, n: int, scale: float = 1.0) -> list[float]:
    """Null-safe, length-normalised, unit-normalised copy of a series."""
    vals = vals or []
    return [float(vals[i]) * scale
            if i < len(vals) and vals[i] is not None else 0.0
            for i in range(n)]


def scaled(vals: list | None, n: int, scale: float = 1.0) -> list[float | None]:
    """Like clean(), but a missing value stays missing.

    Zero-filling is right for generation: a production type the API does not
    report really is contributing nothing. It is wrong for cross-border flows,
    where an unpublished interval would be drawn as a border that briefly
    carried no power — a 15-minute cliff and recovery that never happened. The
    page would rather show a gap than invent an event.
    """
    vals = vals or []
    return [float(vals[i]) * scale
            if i < len(vals) and vals[i] is not None else None
            for i in range(n)]


def r1(x: float) -> float:
    return round(x, 1)


def neighbour_mix(code: str) -> dict[int, dict[str, float]]:
    """Timestamp -> {series id: share of that country's generation}."""
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=FETCH_DAYS + 1)
    payload = get("public_power", country=code, start=start, end=end)
    scale = to_mw(payload)
    out = {}
    for row in payload["data"]:
        ts = int(datetime.fromisoformat(row["timestamp"]).timestamp())
        vals = {k: v * scale for k, v in row["values"].items()
                if k not in NOT_GENERATION and v is not None and v > 0}
        total = sum(vals.values())
        if total > 0:
            out[ts] = {k: v / total for k, v in vals.items()}
    return out


def add_import_mix(out: dict, win: list, times: list,
                   group_series: dict, load: list) -> None:
    """Estimate what the imported power was made of.

    Each border flow is attributed to the exporting country's own generation
    mix at that moment. This is *attribution, not tracing*: it ignores
    transit, so power imported from Czechia that originally came from Poland
    is counted as Czech. Proper flow-tracing needs the whole European
    network. The page says so plainly.
    """
    flows = out.get("_cbpfRaw")
    if not flows:
        return

    mixes = {}
    for sid, code in NEIGHBOURS.items():
        try:
            mixes[code] = neighbour_mix(code)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as e:
            print(f"WARNING: mix for {code} unavailable: {e}", file=sys.stderr)

    if not mixes:
        return

    def nearest(mix: dict, ts: int):
        keys = [k for k in mix if k <= ts]
        return mix[max(keys)] if keys else None

    keys = [g[0] for g in IMPORT_GROUPS]
    stack = {k: [] for k in keys}
    stamps, totals, covered = [], [], []

    for ts, per_border in flows:
        # One unpublished border makes the gross total unknown, not smaller.
        # Summing what is left would draw every group dropping together for a
        # single interval — the whole import mix appearing to vanish and come
        # back. Emit a gap instead.
        if any(mw is None for mw in per_border.values()):
            stamps.append(ts)
            totals.append(None)
            for k in keys:
                stack[k].append(None)
            continue

        att = {k: 0.0 for k in keys}
        imported = 0.0
        matched = 0.0
        for sid, mw in per_border.items():
            if mw <= 0:
                continue
            imported += mw
            mix = nearest(mixes.get(NEIGHBOURS[sid], {}), ts)
            if mix is None:
                continue
            matched += mw
            for series_id, share in mix.items():
                for key, _de, _en, ids in IMPORT_GROUPS:
                    if series_id in ids:
                        att[key] += mw * share
                        break
                else:
                    att["other"] += mw * share
        if imported <= 0 or matched <= 0:
            continue
        stamps.append(ts)
        totals.append(imported)
        covered.append(matched / imported)
        for k in keys:
            stack[k].append(att[k])

    if not stamps:
        return

    # The headline figures describe the newest interval that has one, which
    # is not necessarily the newest interval.
    last = max((i for i, v in enumerate(totals) if v is not None), default=None)
    if last is None:
        return
    now_total = sum(stack[k][last] for k in keys)
    groups = [{
        "key": key, "de": de, "en": en,
        "mw": r1(stack[key][last]),
        "pct": r1(100 * stack[key][last] / now_total) if now_total else 0.0,
        "series": [r1(v) if v is not None else None for v in stack[key]],
    } for key, de, en, _ in IMPORT_GROUPS]

    # Totals over the window, for the headline shares.
    span = {k: sum(v for v in stack[k] if v is not None) for k in keys}
    span_total = sum(span.values()) or 1
    dirty = (span["fossil"] + span["nuclear"]) / span_total * 100

    # Renewable share of everything supplied, domestic plus imports —
    # the consumption-side counterpart to the domestic-only figure.
    dom_ren = dom_all = imp_ren = imp_all = 0.0
    by_ts = {ts: i for i, ts in enumerate(stamps)}
    for i in win:
        ts = times[i]
        j = by_ts.get(ts)
        if j is None or totals[j] is None:
            continue
        dom_ren += sum(group_series[k][i] for k in ("hydro", "wind", "solar", "biomass"))
        dom_all += sum(group_series[k][i] for k, _, _, _ in GROUPS)
        imp_ren += sum(stack[k][j] for k in RENEWABLE_GROUPS)
        imp_all += sum(stack[k][j] for k in keys)

    supply = dom_all + imp_all
    out["importMix"] = {
        "at": stamps[last],
        "t": stamps,
        "groups": groups,
        "total": r1(now_total),
        "fossilNuclearPct": r1(dirty),
        "coverage": r1(min(covered) * 100) if covered else None,
        "gaps": sum(1 for v in totals if v is None),
        "countries": sorted({NEIGHBOURS[s] for _, pb in flows
                             for s, mw in pb.items() if mw is not None and mw > 0}),
        "renewableShareSupply": r1(100 * (dom_ren + imp_ren) / supply) if supply else None,
        "renewableShareDomestic": r1(100 * dom_ren / dom_all) if dom_all else None,
    }


def add_supply_mix(out: dict) -> None:
    """Precompute the donut: one supply total, split into domestic generation
    by source and imports by what those imports are made of.

    The import ring carries the import mix's *shares*, applied to the net
    import figure. The mix itself is measured on gross inflows, which are
    larger than the net balance, so using its megawatts directly would make
    the ring overshoot the supply total the rest of the page is built on.
    """
    imported = max(out["now"]["netImport"], 0.0)
    domestic = out["now"]["generation"]
    supply = domestic + imported
    if supply <= 0:
        return

    rings = {
        "supplyMw": r1(supply),
        "domesticMw": r1(domestic),
        "importedMw": r1(imported),
        "domesticPct": r1(100 * domestic / supply),
        "importedPct": r1(100 * imported / supply),
        "domestic": [{"key": g["key"], "de": g["de"], "en": g["en"],
                      "mw": g["mw"], "pct": r1(100 * g["mw"] / supply)}
                     for g in out["groups"] if g["mw"] > 0],
        "imported": [],
    }

    mix = out.get("importMix")
    if imported > 0 and mix and mix.get("total", 0) > 0:
        for g in mix["groups"]:
            mw = imported * g["mw"] / mix["total"]
            if mw <= 0:
                continue
            rings["imported"].append({
                "key": g["key"], "de": g["de"], "en": g["en"],
                "mw": r1(mw), "pct": r1(100 * mw / supply),
            })
    elif imported > 0:
        # Imports are known, their composition is not: one undifferentiated
        # slice rather than a guess.
        rings["imported"].append({
            "key": "import", "de": "Import", "en": "Import",
            "mw": r1(imported), "pct": r1(100 * imported / supply),
        })

    out["supplyMix"] = rings


def daily_pairs(payload: dict) -> list[tuple[int, float]]:
    """Read a daily series out of either API generation.

    v2 returns rows of {timestamp, values}; the older root endpoints return
    parallel `days` (dd.mm.yyyy) and `data` arrays.
    """
    if payload.get("data") and isinstance(payload["data"], list) \
            and payload["data"] and isinstance(payload["data"][0], dict):
        ids = [s["id"] for s in payload.get("series", [])]
        pairs = []
        for row in payload["data"]:
            values = [row["values"].get(i) for i in ids]
            value = next((v for v in values if v is not None), None)
            if value is None:
                continue
            ts = int(datetime.fromisoformat(row["timestamp"]).timestamp())
            pairs.append((ts, float(value)))
        return pairs

    days = payload.get("days") or []
    data = payload.get("data") or []
    pairs = []
    for day, value in zip(days, data):
        if value is None:
            continue
        try:
            date = datetime.strptime(day, "%d.%m.%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        pairs.append((int(date.timestamp()), float(value)))
    return pairs


def add_season(out: dict) -> None:
    """A year of daily renewable share of load, so today has a season to sit
    in. The rolling seven-day comparison above it cannot show that: a week of
    weather is not a season."""
    payload = None
    for base in (API, API_V1):
        try:
            payload = get("ren_share_daily_avg", base=base, country=COUNTRY, year=-1)
            break
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"WARNING: ren_share_daily_avg via {base}: {e}", file=sys.stderr)
    if payload is None:
        return

    pairs = [p for p in daily_pairs(payload) if p[1] is not None]
    if len(pairs) < 60:
        print(f"WARNING: seasonal series too short ({len(pairs)} days)", file=sys.stderr)
        return
    pairs.sort()
    days = [p[0] for p in pairs]
    values = [p[1] for p in pairs]

    # Daily values are noisy enough to hide the season; the trailing mean is
    # what carries the shape. Thirty days, so it is a month of weather.
    window = 30
    trend_t, trend_v = [], []
    for i in range(window - 1, len(values)):
        trend_t.append(days[i])
        trend_v.append(sum(values[i - window + 1:i + 1]) / window)

    latest = values[-1]
    earlier = values[:-1]
    below = sum(1 for v in earlier if v < latest)
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    best = max(range(len(values)), key=lambda i: values[i])
    worst = min(range(len(values)), key=lambda i: values[i])

    out["season"] = {
        "t": days,
        "values": [r1(v) for v in values],
        "trend": {"t": trend_t, "v": [r1(v) for v in trend_v]},
        "latest": r1(latest),
        "latestAt": days[-1],
        "percentile": r1(100 * below / len(earlier)) if earlier else None,
        "median": r1(median),
        "best": {"value": r1(values[best]), "at": days[best]},
        "worst": {"value": r1(values[worst]), "at": days[worst]},
        "days": len(values),
        "license": payload.get("license", ""),
    }


# River gauges, one per river, each the most downstream inside Austria.
# `hzbnr` is eHYD's station id.
RIVERS = [
    (207373, "Donau", "Danube"),
    (201889, "Inn", "Inn"),
    (203539, "Salzach", "Salzach"),
    (205922, "Enns", "Enns"),
    (213595, "Drau", "Drava"),
    (211490, "Mur", "Mur"),
]
EHYD = "https://ehyd.gv.at/services/Diagram/pegelBgis?hzbnr="
# The sparkline is ~240 px wide, so more points than this buy nothing but
# bytes. Some gauges report every 10 minutes and ship 800+ samples.
RIVER_POINTS = 240


def _river_num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _river_time(s):
    """eHYD stamps readings '06.08.26 18:30' in Austrian local time."""
    try:
        naive = datetime.strptime(str(s), "%d.%m.%y %H:%M")
    except (TypeError, ValueError):
        return None
    try:
        from zoneinfo import ZoneInfo
        return int(naive.replace(tzinfo=ZoneInfo("Europe/Vienna")).timestamp())
    except Exception:                                    # noqa: BLE001
        # Without tz data the hour may be off; the reading is still usable.
        return int(naive.replace(tzinfo=timezone.utc).timestamp())


def add_rivers(out: dict) -> None:
    """Discharge per river, fetched here rather than from the browser.

    This used to be a client-side fetch, which made it the freshest panel on
    the page. eHYD stopped sending `access-control-allow-origin`, so the
    browser call now fails CORS and the panel silently hid itself. Fetching
    server-side costs the freshness edge — the readings are as old as the
    build, up to ~30 min — but they still beat the electricity data by well
    over an hour, and it works.
    """
    gauges = []
    for hzbnr, name_de, name_en in RIVERS:
        try:
            req = urllib.request.Request(f"{EHYD}{hzbnr}",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.load(r)
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, TimeoutError) as e:
            print(f"WARNING: gauge {hzbnr} ({name_en}) unavailable: {e}",
                  file=sys.stderr)
            continue

        now = _river_num(d.get("wert"))
        if now is None:
            continue

        series = [v for v in (_river_num(x) for x in d.get("data") or [])
                  if v is not None]
        if len(series) > RIVER_POINTS:
            stride = len(series) / RIVER_POINTS
            series = [series[int(i * stride)] for i in range(RIVER_POINTS)]

        gauges.append({
            "river": name_de,
            "en": name_en,
            "gauge": d.get("messstelle") or "",
            "unit": d.get("einheit") or "m³/s",
            "now": round(now, 2),
            "at": _river_time(d.get("zp")),
            "nw": _river_num(d.get("niedrigwasser")),
            "mw": _river_num(d.get("mittelwasser")),
            "link": d.get("internet") or None,
            "series": [round(v, 2) for v in series],
        })
        time.sleep(0.5)

    if gauges:
        stamps = [g["at"] for g in gauges if g["at"]]
        out["rivers"] = {"at": max(stamps) if stamps else None, "gauges": gauges}
        print(f"  rivers: {len(gauges)}/{len(RIVERS)} gauges")
    else:
        print("WARNING: no river gauges available", file=sys.stderr)


def stamp_assets() -> None:
    """Rewrite app.js / style.css references in index.html to carry a content
    hash.

    Pages serves assets with `cache-control: max-age=600`, but data.json is
    fetched with a cache-buster and so is always current. Without this, a
    visitor in the ten minutes after a deploy runs the previous JS against
    the new data — fine for a cosmetic change, broken if the shape moved.
    Hashing the URL makes new code and new data arrive together.
    """
    index = OUT.parent / "index.html"
    if not index.exists():
        return
    html = index.read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        path = OUT.parent / name
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
        html = re.sub(rf'{re.escape(name)}(\?v=[0-9a-f]+)?',
                      f"{name}?v={digest}", html)
    index.write_text(html, encoding="utf-8")


def main() -> None:
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=FETCH_DAYS + 1)

    power = get("public_power", country=COUNTRY, start=start, end=end)
    scale = to_mw(power)
    times, cols = columns(power)
    n = len(times)

    # `available_until` is the API's own word on how far the settled data
    # reaches. Prefer it, and fall back to walking back over unpublished
    # nulls — taking the last row blindly can invent a zero-generation moment.
    now_i = -1
    until = power.get("available_until")
    if until:
        until_ts = int(datetime.fromisoformat(until).timestamp())
        now_i = max((i for i, t in enumerate(times) if t <= until_ts), default=-1)
    if now_i < 0:
        for i in range(n - 1, -1, -1):
            if cols.get("load", [None] * n)[i] is not None and cols.get("solar", [None] * n)[i] is not None:
                now_i = i
                break
    if now_i < 0:
        raise SystemExit("no complete sample in public_power response")

    # Fail loudly on series we do not know about rather than silently
    # dropping megawatts out of the mix.
    known = {sid for _, _, _, ids in GROUPS for sid in ids} | NON_GENERATION
    unknown = [sid for sid in cols if sid not in known]
    if unknown:
        print(f"WARNING: unmapped series dropped from the mix: {unknown}", file=sys.stderr)

    group_series = {
        key: [sum(vals) for vals in zip(*(clean(cols.get(sid), n, scale) for sid in ids))]
        for key, _de, _en, ids in GROUPS
    }

    load = clean(cols.get("load"), n, scale)
    pumping = clean(cols.get("hydro_pumped_storage_consumption"), n, scale)  # negative
    trading = clean(cols.get("cross_border_electricity_trading"), n, scale)
    rs_load = cols.get("renewable_share_of_load") or [None] * n
    rs_gen = cols.get("renewable_share_of_generation") or [None] * n

    # Trim to the display window, ending at the last complete sample.
    step_s = times[1] - times[0] if n > 1 else 900
    span = int(HOURS_BACK * 3600 / step_s)
    lo = max(0, now_i - span + 1)
    win = list(range(lo, now_i + 1))

    week_span = int(7 * 24 * 3600 / step_s)
    week_lo = max(0, now_i - week_span + 1)
    week = list(range(week_lo, now_i + 1))

    gen_now = sum(group_series[k][now_i] for k, _, _, _ in GROUPS)
    balance_series = [sum(group_series[k][i] for k, _, _, _ in GROUPS)
                      + trading[i] - load[i] - abs(pumping[i]) for i in win]

    groups_out = [{
        "key": key,
        "de": de,
        "en": en,
        "mw": r1(group_series[key][now_i]),
        "pct": r1(100 * group_series[key][now_i] / gen_now) if gen_now else 0.0,
        "series": [r1(group_series[key][i]) for i in win],
    } for key, de, en, _ in GROUPS]

    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataAt": times[now_i],
        "stepSeconds": step_s,
        "publishedAt": int(datetime.fromisoformat(power["generated_at"]).timestamp())
                       if power.get("generated_at") else None,
        "timezone": power.get("timezone", "Europe/Vienna"),
        "license": power.get("license", ""),
        "now": {
            "load": r1(load[now_i]),
            "generation": r1(gen_now),
            "pumping": r1(abs(pumping[now_i])),
            "netImport": r1(trading[now_i]),
            "renewableShareLoad": r1(rs_load[now_i]) if rs_load[now_i] is not None else None,
            "renewableShareGen": r1(rs_gen[now_i]) if rs_gen[now_i] is not None else None,
        },
        "groups": groups_out,
        "day": {
            "t": [times[i] for i in win],
            "load": [r1(load[i]) for i in win],
            "netImport": [r1(trading[i]) for i in win],
        },
        "balance": {
            "t": [times[i] for i in win],
            "generation": r1(gen_now),
            "netImport": r1(trading[now_i]),
            "load": r1(load[now_i]),
            "gap": r1(balance_series[-1]),
            "series": [r1(v) for v in balance_series],
            "meanAbsGap": r1(sum(abs(v) for v in balance_series) / len(balance_series)),
            "pumping": r1(abs(pumping[now_i])),
        },
        "history": {
            "t": [times[i] for i in week],
            "load": [r1(load[i]) for i in week],
            "netImport": [r1(trading[i]) for i in week],
            "importShare": [r1(100 * max(trading[i], 0.0) / load[i])
                            if load[i] > 0 else 0.0 for i in week],
            "groups": [{
                "key": key, "de": de, "en": en,
                "series": [r1(group_series[key][i]) for i in week],
            } for key, de, en, _ in GROUPS],
        },
    }

    def period_metrics(indices: list[int]) -> dict:
        generation = sum(sum(group_series[k][i] for k, _, _, _ in GROUPS)
                         for i in indices)
        renewable = sum(sum(group_series[k][i]
                            for k in ("hydro", "wind", "solar", "biomass"))
                        for i in indices)
        demand = sum(load[i] for i in indices)
        imports = sum(max(trading[i], 0.0) for i in indices)
        return {
            "avgLoad": sum(load[i] for i in indices) / len(indices),
            "renewablePct": 100 * renewable / generation if generation else 0.0,
            "importShare": 100 * imports / demand if demand else 0.0,
        }

    blocks = []
    samples_per_day = max(1, int(24 * 3600 / step_s))
    for offset in range(7):
        hi = now_i - offset * samples_per_day
        lo_block = max(0, hi - samples_per_day + 1)
        block = list(range(lo_block, hi + 1))
        if len(block) == samples_per_day:
            blocks.append(period_metrics(block))
    if blocks:
        previous = blocks[1:] or blocks
        out["comparison"] = {
            "current": {k: r1(v) for k, v in blocks[0].items()},
            "baseline": {k: r1(sum(b[k] for b in previous) / len(previous))
                         for k in blocks[0]},
            "days": len(previous),
        }

    try:
        flows = get("cbpf", country=COUNTRY, start=start, end=end)
        fscale = to_mw(flows)
        ftimes, fcols = columns(flows)
        names = {s["id"]: s["name"] for s in flows["series"]}

        # Cross-border data runs about an hour further behind than generation,
        # so it gets its own window and its own timestamp rather than being
        # forced onto the generation clock.
        f_until = flows.get("available_until")
        f_now = len(ftimes) - 1
        if f_until:
            until_ts = int(datetime.fromisoformat(f_until).timestamp())
            f_now = max((i for i, t in enumerate(ftimes) if t <= until_ts), default=f_now)

        rows = []
        for sid, vals in fcols.items():
            if sid == "sum":
                continue
            # Walk back to the newest published value for this border.
            for i in range(min(f_now, len(vals) - 1), -1, -1):
                if vals[i] is not None:
                    rows.append({"name": names.get(sid, sid),
                                 "mw": r1(float(vals[i]) * fscale),
                                 "at": ftimes[i]})
                    break
        rows.sort(key=lambda r: -abs(r["mw"]))
        out["flows"] = rows

        fstep = ftimes[1] - ftimes[0] if len(ftimes) > 1 else 900
        fspan = int(HOURS_BACK * 3600 / fstep)
        flo = max(0, f_now - fspan + 1)
        fwin = list(range(flo, f_now + 1))

        # Gaps are kept as nulls from here down: every statistic below skips
        # them rather than counting them as zero flow.
        borders = {sid: scaled(vals, len(ftimes), fscale)
                   for sid, vals in fcols.items() if sid != "sum"}
        complete = [all(b[i] is not None for b in borders.values())
                    for i in range(len(ftimes))]

        # The API's own `sum` is added up over the borders it has, so a
        # missing one does not make it null — it makes it wrong, and low by
        # exactly the missing flow. That is the whole artefact: a border drops
        # out for one interval and the balance appears to swing by a gigawatt.
        # An incomplete interval has an unknown total, so it is a gap here.
        net = [v if complete[i] else None
               for i, v in enumerate(scaled(fcols.get("sum"), len(ftimes), fscale))]
        net_win = [net[i] for i in fwin]
        published = [v for v in net_win if v is not None]

        # Load is on the generation clock; match by timestamp so the
        # import-share figures compare like with like.
        load_at = {times[i]: load[i] for i in range(n)}
        shares = [(net[i] / load_at[ftimes[i]] * 100)
                  for i in fwin
                  if net[i] is not None and net[i] > 0
                  and load_at.get(ftimes[i], 0) > 0]

        peak_imp = max(published, default=0.0)
        peak_exp = min(published, default=0.0)
        importing = sum(1 for v in published if v > 0)

        out["trade"] = {
            "at": ftimes[f_now],
            "t": [ftimes[i] for i in fwin],
            "net": [r1(v) if v is not None else None for v in net_win],
            "countries": [
                {"name": names.get(sid, sid),
                 "series": [r1(series[i]) if series[i] is not None else None
                            for i in fwin]}
                for sid, series in borders.items()
            ],
            "now": r1(net[f_now]) if net[f_now] is not None else None,
            "peakImport": r1(peak_imp),
            "peakExport": r1(peak_exp),
            "peakImportShare": r1(max(shares)) if shares else None,
            "importingSteps": importing,
            # Denominator for "time as a net importer": intervals the source
            # actually published, not intervals on the clock.
            "steps": len(published),
            "gaps": len(net_win) - len(published),
        }
        out["trade"]["countries"].sort(
            key=lambda c: -max((abs(v) for v in c["series"] if v is not None), default=0))

        # Per-border flows over the window, handed to the import-mix step.
        # Stripped again before the file is written.
        out["_cbpfRaw"] = [
            (ftimes[i], {sid: series[i] for sid, series in borders.items()})
            for i in fwin
        ]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as e:
        print(f"WARNING: cross-border flows unavailable: {e}", file=sys.stderr)

    try:
        price = get("price", bzn=BZN, start=start, end=end)
        ptimes, pcols = columns(price)
        pts = [(t, float(v)) for t, v in zip(ptimes, pcols["day_ahead_price"]) if v is not None]
        if pts:
            cutoff = out["dataAt"] - HOURS_BACK * 3600
            recent = [p for p in pts if p[0] >= cutoff] or pts[-96:]
            current = min(pts, key=lambda p: abs(p[0] - out["dataAt"]))
            out["price"] = {
                "unit": price.get("unit", "EUR/MWh"),
                "license": price.get("license", ""),
                "t": [p[0] for p in recent],
                "eur": [r1(p[1]) for p in recent],
                "now": r1(current[1]),
            }
            # What the cross-border balance was worth at day-ahead prices.
            # Commercial trading is used rather than physical flows: money
            # follows trades, not what the wires happen to carry. This is a
            # valuation, not a settlement figure — actual contracts are not
            # all struck at spot.
            by_price = dict(pts)
            hours = step_s / 3600

            storage_indices = [i for i in win if times[i] in by_price]
            if storage_indices:
                storage_generation = [group_series["pumped"][i] for i in storage_indices]
                storage_pumping = [abs(pumping[i]) for i in storage_indices]
                out["storage"] = {
                    "t": [times[i] for i in storage_indices],
                    "generation": [r1(v) for v in storage_generation],
                    "pumping": [r1(v) for v in storage_pumping],
                    "price": [r1(by_price[times[i]]) for i in storage_indices],
                    "nowGeneration": r1(storage_generation[-1]),
                    "nowPumping": r1(storage_pumping[-1]),
                    "peakGeneration": r1(max(storage_generation)),
                    "peakPumping": r1(max(storage_pumping)),
                }

            cost = rev = 0.0
            imp_mwh = exp_mwh = 0.0
            mt, cum = [], []
            for i in win:
                p = by_price.get(times[i])
                if p is None:
                    continue
                mwh = trading[i] * hours
                if mwh > 0:
                    imp_mwh += mwh
                    cost += mwh * p
                else:
                    exp_mwh += -mwh
                    rev += -mwh * p
                mt.append(times[i])
                cum.append(round(cost - rev))

            if mt:
                out["money"] = {
                    "currency": "EUR",
                    "t": mt,
                    "cumulative": cum,
                    "importCost": round(cost),
                    "exportRevenue": round(rev),
                    "net": round(cost - rev),
                    "importMwh": round(imp_mwh),
                    "exportMwh": round(exp_mwh),
                    "avgImportPrice": r1(cost / imp_mwh) if imp_mwh else None,
                    "avgExportPrice": r1(rev / exp_mwh) if exp_mwh else None,
                }
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as e:
        print(f"WARNING: day-ahead price unavailable: {e}", file=sys.stderr)

    add_import_mix(out, win, times, group_series, load)
    out.pop("_cbpfRaw", None)
    add_supply_mix(out)

    try:
        add_season(out)
    except (KeyError, ValueError, TypeError) as e:
        print(f"WARNING: seasonal series unavailable: {e}", file=sys.stderr)

    add_rivers(out)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    stamp_assets()
    stamp = datetime.fromtimestamp(out["dataAt"], timezone.utc)
    print(f"wrote {OUT} — data at {stamp:%Y-%m-%d %H:%M} UTC, "
          f"{out['now']['generation']:.0f} MW generation, {len(win)} samples")


if __name__ == "__main__":
    main()
