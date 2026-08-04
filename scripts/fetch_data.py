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
COUNTRY = "at"
BZN = "AT"
OUT = Path(__file__).resolve().parent.parent / "site" / "data.json"

# How much history the page shows.
HOURS_BACK = 24
# Generation data lags roughly an hour, so over-fetch and trim to the last
# complete sample.
FETCH_DAYS = 2

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


def get(path: str, **params) -> dict:
    """GET with backoff. The API rate-limits (429) when several countries are
    requested back to back, which this script does for the import mix."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{API}/{path}?{qs}",
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

    last = len(stamps) - 1
    now_total = sum(stack[k][last] for k in keys)
    groups = [{
        "key": key, "de": de, "en": en,
        "mw": r1(stack[key][last]),
        "pct": r1(100 * stack[key][last] / now_total) if now_total else 0.0,
        "series": [r1(v) for v in stack[key]],
    } for key, de, en, _ in IMPORT_GROUPS]

    # Totals over the window, for the headline shares.
    span = {k: sum(stack[k]) for k in keys}
    span_total = sum(span.values()) or 1
    dirty = (span["fossil"] + span["nuclear"]) / span_total * 100

    # Renewable share of everything supplied, domestic plus imports —
    # the consumption-side counterpart to the domestic-only figure.
    dom_ren = dom_all = imp_ren = imp_all = 0.0
    by_ts = {ts: i for i, ts in enumerate(stamps)}
    for i in win:
        ts = times[i]
        j = by_ts.get(ts)
        if j is None:
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
        "coverage": r1(min(covered) * 100),
        "countries": sorted({NEIGHBOURS[s] for _, pb in flows for s, mw in pb.items() if mw > 0}),
        "renewableShareSupply": r1(100 * (dom_ren + imp_ren) / supply) if supply else None,
        "renewableShareDomestic": r1(100 * dom_ren / dom_all) if dom_all else None,
    }


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

    gen_now = sum(group_series[k][now_i] for k, _, _, _ in GROUPS)

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

        net = clean(fcols.get("sum"), len(ftimes), fscale)
        net_win = [net[i] for i in fwin]

        # Load is on the generation clock; match by timestamp so the
        # import-share figures compare like with like.
        load_at = {times[i]: load[i] for i in range(n)}
        shares = [(net[i] / load_at[ftimes[i]] * 100)
                  for i in fwin
                  if net[i] > 0 and load_at.get(ftimes[i], 0) > 0]

        peak_imp = max(net_win, default=0.0)
        peak_exp = min(net_win, default=0.0)
        importing = sum(1 for v in net_win if v > 0)

        out["trade"] = {
            "at": ftimes[f_now],
            "t": [ftimes[i] for i in fwin],
            "net": [r1(v) for v in net_win],
            "countries": [
                {"name": names.get(sid, sid),
                 "series": [r1(v) for v in
                            (lambda c: [c[i] for i in fwin])(clean(vals, len(ftimes), fscale))]}
                for sid, vals in fcols.items() if sid != "sum"
            ],
            "now": r1(net[f_now]),
            "peakImport": r1(peak_imp),
            "peakExport": r1(peak_exp),
            "peakImportShare": r1(max(shares)) if shares else None,
            "importingSteps": importing,
            "steps": len(fwin),
        }
        out["trade"]["countries"].sort(key=lambda c: -max(abs(v) for v in c["series"]))

        # Per-border flows over the window, handed to the import-mix step.
        # Stripped again before the file is written.
        out["_cbpfRaw"] = [
            (ftimes[i], {sid: clean(vals, len(ftimes), fscale)[i]
                         for sid, vals in fcols.items() if sid != "sum"})
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    stamp_assets()
    stamp = datetime.fromtimestamp(out["dataAt"], timezone.utc)
    print(f"wrote {OUT} — data at {stamp:%Y-%m-%d %H:%M} UTC, "
          f"{out['now']['generation']:.0f} MW generation, {len(win)} samples")


if __name__ == "__main__":
    main()
