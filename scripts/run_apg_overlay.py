#!/usr/bin/env python3
"""Run the APG overlay with short, IPv4-only network diagnostics.

This wrapper exists because GitHub-hosted runners timed out before receiving
any HTTP response from transparency.apg.at. It keeps the normal overlay logic
but makes connectivity failures fast and observable.
"""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request

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

    # Six hours comfortably bridges the observed 2-4 h Energy-Charts lag while
    # reducing APG payload size and request count versus the original 30 h.
    overlay_apg.LOOKBACK_HOURS = 6
    overlay_apg.get_json = quick_get_json
    overlay_apg.main()


if __name__ == "__main__":
    main()
