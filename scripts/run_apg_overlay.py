#!/usr/bin/env python3
"""Run the APG overlay with short, IPv4-only network diagnostics.

This wrapper exists because GitHub-hosted runners timed out before receiving
any HTTP response from transparency.apg.at. It also enforces a live-API
constraint that is stricter than the OpenAPI description: APG Data requests
must use local-midnight boundaries for fromlocal/tolocal.
"""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import overlay_apg

HOST = "transparency.apg.at"
SWAGGER = "https://transparency.apg.at/api/swagger/v1/swagger.json"
REQUEST_TIMEOUT = 8
ATTEMPTS = 2

_original_getaddrinfo = socket.getaddrinfo


def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


def describe_dns() -> None:
    try:
        infos = _original_getaddrinfo(HOST, 443, 0, socket.SOCK_STREAM)
        seen = []
        for family, _type, _proto, _canonname, sockaddr in infos:
            label = "IPv6" if family == socket.AF_INET6 else "IPv4" if family == socket.AF_INET else str(family)
            value = sockaddr[0]
            item = f"{label} {value}"
            if item not in seen:
                seen.append(item)
        print("APG DNS: " + ", ".join(seen))
    except OSError as exc:
        print(f"WARNING: APG DNS lookup failed: {exc}", file=sys.stderr)


def quick_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "woher-kommt-der-strom/1.0",
    })
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        started = time.monotonic()
        print(f"APG GET attempt {attempt + 1}/{ATTEMPTS}: {url}")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                payload = json.load(response)
            elapsed = time.monotonic() - started
            print(f"APG GET ok in {elapsed:.1f}s: HTTP {response.status}")
            return payload.get("ResponseData", payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            elapsed = time.monotonic() - started
            last = exc
            print(f"WARNING: APG GET failed after {elapsed:.1f}s: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500 and exc.code != 429:
                raise
            if attempt + 1 < ATTEMPTS:
                time.sleep(1)
    raise last if last else RuntimeError("APG request failed")


def midnight(value: datetime) -> datetime:
    local = value.astimezone(overlay_apg.TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def day_aligned_fetch_series(kind: str, start: datetime, end: datetime) -> dict:
    """Fetch whole local days, then let overlay_apg select the useful tail.

    The live APG Data API rejects intra-day fromlocal/tolocal values even
    though the OpenAPI parameter description is more permissive. Both path
    timestamps therefore stay at 00:00 local time. A six-hour lookback usually
    costs one request per series, or two when it crosses midnight.
    """
    first_day = midnight(start)
    last_boundary = midnight(end)
    if end > last_boundary:
        last_boundary += timedelta(days=1)

    rows: list[dict] = []
    columns: list[dict] | None = None
    versions: list[str] = []
    cursor = first_day
    while cursor < last_boundary:
        next_day = cursor + timedelta(days=1)
        url = (f"{overlay_apg.APG}/{kind}/Data/{overlay_apg.LANGUAGE}/"
               f"{overlay_apg.RESOLUTION}/{overlay_apg.local_arg(cursor)}/"
               f"{overlay_apg.local_arg(next_day)}")
        payload = overlay_apg.get_json(url)
        cols = payload.get("ValueColumns") or []
        if columns is None:
            columns = cols
        elif [c.get("InternalName") for c in columns] != [c.get("InternalName") for c in cols]:
            raise ValueError(f"APG {kind} columns changed across days")
        rows.extend(payload.get("ValueRows") or [])
        if payload.get("VersionInformation"):
            versions.append(str(payload["VersionInformation"]))
        cursor = next_day

    return {
        "ValueColumns": columns or [],
        "ValueRows": rows,
        "VersionInformation": versions[-1] if versions else None,
    }


def main() -> None:
    describe_dns()

    # Force all subsequent transparency.apg.at connections through IPv4. If
    # the previous timeout was caused by a broken IPv6 route, this isolates it.
    socket.getaddrinfo = ipv4_getaddrinfo

    try:
        print("APG probe: Swagger over IPv4")
        quick_get_json(SWAGGER)
    except Exception as exc:
        print(f"WARNING: APG IPv4 probe failed; keeping Energy-Charts data: {exc}",
              file=sys.stderr)
        return

    # Six hours comfortably bridges the observed 2-4 h Energy-Charts lag. APG
    # itself receives whole-day requests; this lookback only controls which
    # local calendar day(s) we need to fetch.
    overlay_apg.LOOKBACK_HOURS = 6
    overlay_apg.get_json = quick_get_json
    overlay_apg.fetch_series = day_aligned_fetch_series
    overlay_apg.main()


if __name__ == "__main__":
    main()
