#!/usr/bin/env python3
"""Overlay fresher Austrian APG transparency data onto site/data.json.

Energy-Charts remains the broad/fallback source. This script fetches APG's
15-minute Austrian generation, actual load and physical cross-border flows,
then appends samples newer than Energy-Charts' `dataAt`. If APG is unavailable
or incomplete, data.json is left untouched and the build keeps the existing
Energy-Charts result.
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

APG = "https://transparency.apg.at/api/v1"
OUT = Path(__file__).resolve().parent.parent / "site" / "data.json"
TZ = ZoneInfo("Europe/Vienna")
RESOLUTION = "PT15M"
LANGUAGE = "English"
LOOKBACK_HOURS = 30

GEN_GROUPS = {
    "hydro": ("B11", "B12"),
    "fossil": ("B04", "B05", "B06"),
    "wind": ("B19",),
    "pumped": ("B10",),
    "biomass": ("B01", "B17"),
    "other": ("B09", "B15", "B20"),
}
RENEWABLE_GROUPS = {"hydro", "wind", "solar", "biomass"}
BORDERS = {
    "CZtoAT": "Czech Republic",
    "DEtoAT": "Germany",
    "HUtoAT": "Hungary",
    "ITtoAT": "Italy",
    "SItoAT": "Slovenia",
    "CHtoAT": "Switzerland",
}


def r1(value: float) -> float:
    return round(float(value), 1)


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "woher-kommt-der-strom/1.0",
    })
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.load(response)
            return payload.get("ResponseData", payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500 and exc.code != 429:
                raise
            time.sleep(2 * (attempt + 1))
    raise last if last else RuntimeError("APG request failed")


def local_arg(value: datetime) -> str:
    return value.astimezone(TZ).strftime("%Y-%m-%dT%H%M%S")


def fetch_series(kind: str, start: datetime, end: datetime) -> dict:
    """Fetch an APG Data endpoint in chunks shorter than its one-day limit."""
    rows: list[dict] = []
    columns: list[dict] | None = None
    versions: list[str] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(hours=23, minutes=45), end)
        url = (f"{APG}/{kind}/Data/{LANGUAGE}/{RESOLUTION}/"
               f"{local_arg(cursor)}/{local_arg(chunk_end)}")
        payload = get_json(url)
        cols = payload.get("ValueColumns") or []
        if columns is None:
            columns = cols
        elif [c.get("InternalName") for c in columns] != [c.get("InternalName") for c in cols]:
            raise ValueError(f"APG {kind} columns changed across chunks")
        rows.extend(payload.get("ValueRows") or [])
        if payload.get("VersionInformation"):
            versions.append(str(payload["VersionInformation"]))
        cursor = chunk_end
    return {
        "ValueColumns": columns or [],
        "ValueRows": rows,
        "VersionInformation": versions[-1] if versions else None,
    }


def row_timestamp(row: dict, previous: int | None = None) -> int:
    naive = datetime.strptime(f"{row['DF']} {row['TF']}", "%d.%m.%Y %H:%M")
    candidates = sorted({int(naive.replace(tzinfo=TZ, fold=fold).timestamp())
                         for fold in (0, 1)})
    if previous is not None:
        later = [stamp for stamp in candidates if stamp > previous]
        if later:
            return min(later)
    return candidates[0]


def parse(payload: dict) -> dict[int, dict[str, float | None]]:
    names = [column.get("InternalName") for column in payload.get("ValueColumns", [])]
    result: dict[int, dict[str, float | None]] = {}
    previous: int | None = None
    for row in payload.get("ValueRows", []):
        try:
            stamp = row_timestamp(row, previous)
        except (KeyError, ValueError):
            continue
        previous = stamp
        values = row.get("V") or []
        parsed: dict[str, float | None] = {}
        for index, name in enumerate(names):
            if not name:
                continue
            item = values[index] if index < len(values) and isinstance(values[index], dict) else {}
            value = item.get("V")
            parsed[name] = (None if value is None or item.get("E") or item.get("M")
                            else float(value))
        result[stamp] = parsed
    return result


def generation_groups(row: dict[str, float | None]) -> dict[str, float] | None:
    solar_key = "SolarTotal" if "SolarTotal" in row else "B16"
    required = {series for ids in GEN_GROUPS.values() for series in ids}
    required.add(solar_key)
    if any(row.get(series) is None for series in required):
        return None
    groups = {key: sum(float(row[series]) for series in ids)
              for key, ids in GEN_GROUPS.items()}
    groups["solar"] = float(row[solar_key])
    return groups


def complete_border_row(row: dict[str, float | None]) -> bool:
    return row.get("Sum") is not None and all(row.get(series) is not None for series in BORDERS)


def append_trim(times: list, series: list, additions: list[tuple[int, float]],
                seconds: int) -> tuple[list, list]:
    by_time = {int(stamp): value for stamp, value in zip(times, series)}
    by_time.update({int(stamp): r1(value) for stamp, value in additions})
    ordered = sorted(by_time)
    if not ordered:
        return [], []
    cutoff = ordered[-1] - seconds
    ordered = [stamp for stamp in ordered if stamp >= cutoff]
    return ordered, [by_time[stamp] for stamp in ordered]


def recompute_supply_mix(data: dict) -> None:
    domestic = float(data["now"]["generation"])
    imported = max(float(data["now"]["netImport"]), 0.0)
    supply = domestic + imported
    if supply <= 0:
        return
    result = {
        "supplyMw": r1(supply),
        "domesticMw": r1(domestic),
        "importedMw": r1(imported),
        "domesticPct": r1(100 * domestic / supply),
        "importedPct": r1(100 * imported / supply),
        "domestic": [],
        "imported": [],
    }
    for group in data.get("groups", []):
        mw = float(group.get("mw", 0))
        if mw > 0:
            result["domestic"].append({
                "key": group["key"], "de": group["de"], "en": group["en"],
                "mw": r1(mw), "pct": r1(100 * mw / supply),
            })
    mix = data.get("importMix") or {}
    mix_total = float(mix.get("total") or 0)
    if imported > 0 and mix_total > 0:
        for group in mix.get("groups", []):
            mw = imported * float(group.get("mw") or 0) / mix_total
            if mw > 0:
                result["imported"].append({
                    "key": group["key"], "de": group["de"], "en": group["en"],
                    "mw": r1(mw), "pct": r1(100 * mw / supply),
                })
    elif imported > 0:
        result["imported"].append({
            "key": "import", "de": "Import", "en": "Import",
            "mw": r1(imported), "pct": r1(100 * imported / supply),
        })
    data["supplyMix"] = result


def update_comparison(data: dict) -> None:
    history = data.get("history") or {}
    times = history.get("t") or []
    load = history.get("load") or []
    net = history.get("netImport") or []
    groups = {group["key"]: group.get("series", []) for group in history.get("groups", [])}
    if len(times) < 96:
        return
    blocks = []
    for offset in range(7):
        high = len(times) - offset * 96
        low = high - 96
        if low < 0:
            break
        indices = range(low, high)
        generation = sum(sum(groups[key][i] for key in groups) for i in indices)
        renewable = sum(sum(groups[key][i] for key in RENEWABLE_GROUPS if key in groups)
                        for i in indices)
        demand = sum(load[i] for i in indices)
        imports = sum(max(net[i], 0.0) for i in indices)
        blocks.append({
            "avgLoad": demand / 96,
            "renewablePct": 100 * renewable / generation if generation else 0,
            "importShare": 100 * imports / demand if demand else 0,
        })
    if not blocks:
        return
    previous = blocks[1:] or blocks
    data["comparison"] = {
        "current": {key: r1(value) for key, value in blocks[0].items()},
        "baseline": {key: r1(sum(block[key] for block in previous) / len(previous))
                     for key in blocks[0]},
        "days": len(previous),
    }


def main() -> None:
    if not OUT.exists():
        raise SystemExit(f"missing {OUT}; run fetch_data.py first")
    data = json.loads(OUT.read_text(encoding="utf-8"))
    energy_charts_at = int(data.get("dataAt") or 0)

    end = datetime.now(TZ).replace(second=0, microsecond=0)
    start = end - timedelta(hours=LOOKBACK_HOURS)
    try:
        generation_payload = fetch_series("AGPT", start, end)
        load_payload = fetch_series("AL", start, end)
        border_payload = fetch_series("CBPF", start, end)
        generation = parse(generation_payload)
        load = parse(load_payload)
        borders = parse(border_payload)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            ValueError, KeyError) as exc:
        print(f"WARNING: APG overlay unavailable; keeping Energy-Charts data: {exc}",
              file=sys.stderr)
        return

    common: list[tuple[int, dict[str, float], float, float]] = []
    for stamp in sorted(set(generation) & set(load) & set(borders)):
        if stamp <= energy_charts_at:
            continue
        groups = generation_groups(generation[stamp])
        load_value = load[stamp].get("AL")
        if groups is None or load_value is None or not complete_border_row(borders[stamp]):
            continue
        common.append((stamp, groups, float(load_value), float(borders[stamp]["Sum"])))

    if not common:
        print("APG has no newer complete common sample; keeping Energy-Charts head",
              file=sys.stderr)
        return

    accepted: list[tuple[int, dict[str, float], float, float]] = []
    previous_generation = float(data["now"]["generation"])
    for sample in common:
        total = sum(sample[1].values())
        if not math.isfinite(total) or total <= 0 or abs(total - previous_generation) > 5000:
            print(f"WARNING: rejecting implausible APG generation at {sample[0]}: "
                  f"{total:.1f} MW", file=sys.stderr)
            break
        accepted.append(sample)
        previous_generation = total
    if not accepted:
        return

    group_by_key = {group["key"]: group for group in data["groups"]}
    additions_by_group = {key: [] for key in group_by_key}
    load_add: list[tuple[int, float]] = []
    net_add: list[tuple[int, float]] = []
    for stamp, groups, load_value, net_value in accepted:
        for key in additions_by_group:
            additions_by_group[key].append((stamp, groups.get(key, 0.0)))
        load_add.append((stamp, load_value))
        net_add.append((stamp, net_value))

    original_day_t = data["day"]["t"]
    for key, group in group_by_key.items():
        _, group["series"] = append_trim(original_day_t, group["series"],
                                         additions_by_group[key], 24 * 3600)
    day_t, day_load = append_trim(original_day_t, data["day"]["load"],
                                  load_add, 24 * 3600)
    _, day_net = append_trim(original_day_t, data["day"]["netImport"],
                             net_add, 24 * 3600)
    data["day"]["t"], data["day"]["load"], data["day"]["netImport"] = day_t, day_load, day_net

    latest_stamp, latest_groups, latest_load, latest_net = accepted[-1]
    total_generation = sum(latest_groups.values())
    renewable = sum(latest_groups.get(key, 0.0) for key in RENEWABLE_GROUPS)
    for key, group in group_by_key.items():
        mw = latest_groups.get(key, 0.0)
        group["mw"] = r1(mw)
        group["pct"] = r1(100 * mw / total_generation) if total_generation else 0.0
    data["now"]["generation"] = r1(total_generation)
    data["now"]["load"] = r1(latest_load)
    data["now"]["netImport"] = r1(latest_net)
    data["now"]["renewableShareGen"] = r1(100 * renewable / total_generation)
    data["now"]["renewableShareLoad"] = r1(100 * renewable / latest_load)
    data["dataAt"] = latest_stamp

    history = data.get("history")
    if history:
        original_history_t = history["t"]
        new_t, new_load = append_trim(original_history_t, history["load"],
                                      load_add, 7 * 24 * 3600)
        _, new_net = append_trim(original_history_t, history["netImport"],
                                 net_add, 7 * 24 * 3600)
        history["t"], history["load"], history["netImport"] = new_t, new_load, new_net
        history["importShare"] = [r1(100 * max(net_value, 0.0) / load_value)
                                  if load_value > 0 else 0.0
                                  for load_value, net_value in zip(new_load, new_net)]
        for group in history.get("groups", []):
            _, group["series"] = append_trim(original_history_t, group["series"],
                                              additions_by_group[group["key"]],
                                              7 * 24 * 3600)
        update_comparison(data)

    complete_borders = [(stamp, row) for stamp, row in sorted(borders.items())
                        if complete_border_row(row)]
    if complete_borders:
        cutoff = complete_borders[-1][0] - 24 * 3600
        recent = [(stamp, row) for stamp, row in complete_borders if stamp >= cutoff]
        trade_t = [stamp for stamp, _ in recent]
        trade_net = [r1(row["Sum"]) for _, row in recent]
        shares = [row["Sum"] / load[stamp]["AL"] * 100
                  for stamp, row in recent
                  if row["Sum"] > 0 and stamp in load and load[stamp].get("AL")]
        data["trade"] = {
            **(data.get("trade") or {}),
            "at": trade_t[-1],
            "t": trade_t,
            "net": trade_net,
            "countries": [
                {"name": name, "series": [r1(row[series]) for _, row in recent]}
                for series, name in BORDERS.items()
            ],
            "now": trade_net[-1],
            "peakImport": r1(max(trade_net, default=0.0)),
            "peakExport": r1(min(trade_net, default=0.0)),
            "peakImportShare": r1(max(shares)) if shares else None,
            "importingSteps": sum(1 for value in trade_net if value > 0),
            "steps": len(trade_net),
            "gaps": 0,
        }
        last_stamp, last_row = complete_borders[-1]
        data["flows"] = sorted([
            {"name": name, "mw": r1(last_row[series]), "at": last_stamp}
            for series, name in BORDERS.items()
        ], key=lambda row: -abs(row["mw"]))

    pumping = float(data["now"].get("pumping") or 0)
    balance_add = [(stamp, sum(groups.values()) + net_value - load_value - pumping)
                   for stamp, groups, load_value, net_value in accepted]
    gap = balance_add[-1][1]
    balance = data.get("balance") or {}
    balance["generation"] = r1(total_generation)
    balance["netImport"] = r1(latest_net)
    balance["load"] = r1(latest_load)
    balance["gap"] = r1(gap)
    if balance.get("t") and balance.get("series"):
        balance["t"], balance["series"] = append_trim(balance["t"], balance["series"],
                                                       balance_add, 24 * 3600)
        balance["meanAbsGap"] = r1(sum(abs(value) for value in balance["series"])
                                   / len(balance["series"]))
    data["balance"] = balance

    recompute_supply_mix(data)
    if data.get("importMix"):
        data["importMix"]["renewableShareDomestic"] = r1(100 * renewable / total_generation)

    data["sources"] = {
        "primary": "apg",
        "apg": {
            "generationAt": latest_stamp,
            "loadAt": latest_stamp,
            "cbpfAt": complete_borders[-1][0] if complete_borders else None,
            "generationVersion": generation_payload.get("VersionInformation"),
            "loadVersion": load_payload.get("VersionInformation"),
            "cbpfVersion": border_payload.get("VersionInformation"),
        },
        "energyCharts": {
            "dataAt": energy_charts_at,
            "publishedAt": data.get("publishedAt"),
        },
    }

    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n",
                   encoding="utf-8")
    lag_minutes = (datetime.now(TZ).timestamp() - latest_stamp) / 60
    improvement = (latest_stamp - energy_charts_at) / 60
    print(f"APG overlay: latest complete sample {lag_minutes:.0f} min old; "
          f"{improvement:.0f} min newer than Energy-Charts")


if __name__ == "__main__":
    main()
