#!/usr/bin/env python3
"""Mirror the VPS SQLite nowcast exports into the Pages artifact."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("NOWCAST_EXPORT_BASE_URL", "https://strom-api.rfuzzo.de/apg")
MAX_AGE_SECONDS = 60 * 60


def fetch(name: str) -> dict:
    request = urllib.request.Request(
        f"{BASE_URL}/{name}",
        headers={
            "Accept": "application/json",
            "User-Agent": "woher-kommt-der-strom-github/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f"{name} returned HTTP {response.status}")
        return json.load(response)


def validate(nowcast: dict, history: dict) -> None:
    if nowcast.get("schemaVersion") != 2 or not isinstance(nowcast.get("models"), dict):
        raise ValueError("invalid VPS nowcast export")
    if history.get("schemaVersion") != 1 or not isinstance(history.get("predictions"), list):
        raise ValueError("invalid VPS nowcast-history export")
    updated_at = history.get("updatedAt")
    if not isinstance(updated_at, (int, float)):
        raise ValueError("VPS nowcast history has no updatedAt timestamp")
    age = int(time.time() - updated_at)
    if age < -300 or age > MAX_AGE_SECONDS:
        raise ValueError(f"VPS nowcast history age is invalid ({age}s)")


def write(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    try:
        nowcast = fetch("nowcast.json")
        history = fetch("nowcast-history.json")
        validate(nowcast, history)
    except Exception as exc:
        print(
            f"WARNING: VPS nowcast exports unavailable; preserving prior history: {exc}",
            file=sys.stderr,
        )
        return
    write(ROOT / "site" / "nowcast.json", nowcast)
    write(ROOT / "site" / "nowcast-history.json", history)
    summary = history.get("summary", {})
    print(
        f"VPS nowcasts: model={nowcast.get('model')}, "
        f"{summary.get('scoredCount', 0)} scored, "
        f"{summary.get('pendingCount', 0)} pending"
    )


if __name__ == "__main__":
    main()
