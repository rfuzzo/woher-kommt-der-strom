#!/usr/bin/env python3
"""Fetch APG transparency data and atomically publish a schema-v4 cache file."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


APG_HOST = os.environ.get("APG_HOST", "https://transparency.apg.at")
OUTPUT = Path(os.environ.get("APG_CACHE_OUTPUT", "/var/lib/apg-cache/latest.json"))
REGION = os.environ.get("APG_CACHE_REGION", "netcup-vps")
TIMEOUT_SECONDS = 30
FETCH_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1
TZ = ZoneInfo("Europe/Vienna")
KINDS = {
    "generation": "AGPT",
    "load": "AL",
    "borders": "CBPF",
    "generationForecast": "DAFTG",
    "loadForecast": "ALF",
}
PRODUCTS = {"loadForecast": "DALF"}


def fetch_json(url: str) -> Any:
    last_error: Optional[Exception] = None
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "woher-kommt-der-strom-vps-cache/1.0",
        },
    )
    for attempt in range(FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise RuntimeError(f"APG returned HTTP {response.status}")
                return json.load(response)
        except Exception as exc:  # Keep the last good file on every fetch failure.
            last_error = exc
            if attempt + 1 < FETCH_ATTEMPTS:
                print(f"APG fetch failed; retrying: {exc}", file=sys.stderr)
                time.sleep(RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def unwrap(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("APG response is not an object")
    data = payload.get("ResponseData", payload)
    if not isinstance(data, dict):
        raise ValueError("APG ResponseData is not an object")
    columns = data.get("ValueColumns")
    rows = data.get("ValueRows")
    if not isinstance(columns, list) or not columns:
        raise ValueError("APG response has no ValueColumns")
    if not isinstance(rows, list):
        raise ValueError("APG response has no ValueRows")
    return {
        "ValueColumns": columns,
        "ValueRows": rows,
        "VersionInformation": data.get("VersionInformation"),
    }


def merge_days(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_names = [column.get("InternalName") for column in first["ValueColumns"]]
    second_names = [column.get("InternalName") for column in second["ValueColumns"]]
    if first_names != second_names:
        raise ValueError("APG ValueColumns changed between adjacent days")
    return {
        "ValueColumns": second["ValueColumns"],
        "ValueRows": [*first["ValueRows"], *second["ValueRows"]],
        "VersionInformation": second.get("VersionInformation")
        or first.get("VersionInformation"),
    }


def fetch_kind(
    kind: str,
    yesterday: date,
    today: date,
    tomorrow: date,
    product: str | None = None,
) -> dict[str, Any]:
    product_path = f"/{product}" if product else ""
    base = f"{APG_HOST}/api/v1/{kind}/Data{product_path}/English/PT15M"
    previous = unwrap(fetch_json(f"{base}/{yesterday.isoformat()}T000000/{today.isoformat()}T000000"))
    current = unwrap(fetch_json(f"{base}/{today.isoformat()}T000000/{tomorrow.isoformat()}T000000"))
    return merge_days(previous, current)


def build_cache(now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(TZ).date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    def fetch(item: tuple[str, str]) -> tuple[str, dict[str, Any]]:
        name, kind = item
        return name, fetch_kind(kind, yesterday, today, tomorrow, PRODUCTS.get(name))

    with ThreadPoolExecutor(max_workers=len(KINDS)) as pool:
        datasets = dict(pool.map(fetch, KINDS.items()))

    fetched_at_epoch = int(datetime.now(timezone.utc).timestamp())
    return {
        "schemaVersion": 4,
        "fetchedAt": datetime.fromtimestamp(fetched_at_epoch, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "fetchedAtEpoch": fetched_at_epoch,
        "region": REGION,
        "window": {"from": yesterday.isoformat(), "to": tomorrow.isoformat()},
        **datasets,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o644)
    os.replace(temporary, path)


def main() -> None:
    payload = build_cache()
    atomic_write_json(OUTPUT, payload)
    rows = "/".join(str(len(payload[name]["ValueRows"])) for name in KINDS)
    print(f"APG cache refreshed at {payload['fetchedAt']}; rows {rows}; wrote {OUTPUT}")


if __name__ == "__main__":
    main()
