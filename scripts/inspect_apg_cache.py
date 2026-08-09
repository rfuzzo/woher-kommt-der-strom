#!/usr/bin/env python3
"""Report per-feed freshness from the Deno APG cache.

This is diagnostic only: it never mutates site/data.json and never fails a deploy.
It shows which APG feed currently limits the common timestamp used by the overlay.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CACHE_URL = os.environ.get(
    "APG_CACHE_URL",
    "https://woher-kommt-der-strom.rfuzzo.deno.net/apg/latest.json",
)
TZ = ZoneInfo("Europe/Vienna")

GEN_REQUIRED = {
    "B01", "B04", "B05", "B06", "B09", "B10", "B11", "B12",
    "B15", "B17", "B19", "B20",
}
BORDER_REQUIRED = {"Sum", "CZtoAT", "DEtoAT", "HUtoAT", "ITtoAT", "SItoAT", "CHtoAT"}


def fetch() -> dict:
    req = urllib.request.Request(CACHE_URL, headers={
        "Accept": "application/json",
        "User-Agent": "woher-kommt-der-strom-diagnostics/1.0",
    })
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.load(response)


def row_stamp(row: dict) -> int | None:
    try:
        naive = datetime.strptime(f"{row['DF']} {row['TF']}", "%d.%m.%Y %H:%M")
    except (KeyError, ValueError):
        return None
    # Ambiguous DST rows can map to two instants. For freshness diagnostics the
    # later fold is the conservative/latest interpretation.
    return max(int(naive.replace(tzinfo=TZ, fold=fold).timestamp()) for fold in (0, 1))


def rows_by_stamp(dataset: dict) -> dict[int, dict[str, float | None]]:
    names = [c.get("InternalName") for c in dataset.get("ValueColumns", [])]
    result: dict[int, dict[str, float | None]] = {}
    for row in dataset.get("ValueRows", []):
        stamp = row_stamp(row)
        if stamp is None:
            continue
        values = row.get("V") or []
        parsed: dict[str, float | None] = {}
        for i, name in enumerate(names):
            if not name:
                continue
            item = values[i] if i < len(values) and isinstance(values[i], dict) else {}
            value = item.get("V")
            parsed[name] = None if value is None or item.get("E") or item.get("M") else float(value)
        result[stamp] = parsed
    return result


def generation_usable(row: dict[str, float | None]) -> bool:
    solar = "SolarTotal" if "SolarTotal" in row else "B16"
    return solar in row and row.get(solar) is not None and all(row.get(k) is not None for k in GEN_REQUIRED)


def load_usable(row: dict[str, float | None]) -> bool:
    return row.get("AL") is not None


def borders_usable(row: dict[str, float | None]) -> bool:
    return all(row.get(k) is not None for k in BORDER_REQUIRED)


def fmt(stamp: int | None, now: int) -> str:
    if stamp is None:
        return "none"
    local = datetime.fromtimestamp(stamp, TZ).strftime("%Y-%m-%d %H:%M %Z")
    return f"{local} ({max(0, now - stamp) // 60} min old)"


def main() -> None:
    payload = fetch()
    now = int(datetime.now(timezone.utc).timestamp())
    feeds = {
        "generation": (rows_by_stamp(payload["generation"]), generation_usable),
        "load": (rows_by_stamp(payload["load"]), load_usable),
        "borders": (rows_by_stamp(payload["borders"]), borders_usable),
    }

    usable_sets: dict[str, set[int]] = {}
    for name, (rows, predicate) in feeds.items():
        published = max(rows, default=None)
        usable = {stamp for stamp, row in rows.items() if predicate(row)}
        usable_sets[name] = usable
        newest_usable = max(usable, default=None)
        print(f"APG {name:10s} published: {fmt(published, now)}")
        print(f"APG {name:10s} usable:    {fmt(newest_usable, now)}")

    common = set.intersection(*usable_sets.values()) if usable_sets else set()
    newest_common = max(common, default=None)
    print(f"APG common     usable:    {fmt(newest_common, now)}")

    if newest_common is not None:
        blockers = []
        for name, usable in usable_sets.items():
            latest = max(usable, default=0)
            if latest == newest_common:
                blockers.append(name)
        print("APG common timestamp limited by: " + ", ".join(blockers))


if __name__ == "__main__":
    main()
