#!/usr/bin/env python3
"""Overlay fresher APG data fetched from a validated cache onto site/data.json.

Energy-Charts remains the production fallback. This wrapper downloads one
validated cache payload, checks schema/freshness, then reuses the existing
overlay_apg parsing and merge logic without making any direct APG requests
from GitHub-hosted runners. The Netcup VPS is primary and Deno is retained as
an independent fallback during the migration.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import overlay_apg

DEFAULT_CACHE_URLS = (
    "https://strom-api.rfuzzo.de/apg/latest.json",
    "https://woher-kommt-der-strom.rfuzzo.deno.net/apg/latest.json",
)
MAX_CACHE_AGE_SECONDS = 60 * 60
TIMEOUT_SECONDS = 12
SUPPORTED_SCHEMAS = {3, 4}


def cache_urls() -> tuple[str, ...]:
    configured = os.environ.get("APG_CACHE_URLS")
    if configured:
        urls = tuple(url.strip() for url in configured.split(",") if url.strip())
        if urls:
            return urls
    legacy = os.environ.get("APG_CACHE_URL")
    return (legacy,) if legacy else DEFAULT_CACHE_URLS


def fetch_one(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "woher-kommt-der-strom-github/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"cache returned HTTP {response.status}")
        payload = json.load(response)

    schema = payload.get("schemaVersion")
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError(f"unsupported APG cache schema: {schema!r}")

    fetched_at = payload.get("fetchedAtEpoch")
    if not isinstance(fetched_at, (int, float)):
        raise ValueError("APG cache has no numeric fetchedAtEpoch")
    age = int(datetime.now(timezone.utc).timestamp() - fetched_at)
    if age < -300:
        raise ValueError(f"APG cache timestamp is {abs(age)}s in the future")
    if age > MAX_CACHE_AGE_SECONDS:
        raise ValueError(f"APG cache is stale ({age // 60} min old)")

    for name in ("generation", "load", "borders", "generationForecast"):
        dataset = payload.get(name)
        if not isinstance(dataset, dict):
            raise ValueError(f"APG cache missing {name}")
        if not dataset.get("ValueColumns") or not dataset.get("ValueRows"):
            raise ValueError(f"APG cache {name} is empty")
    if schema >= 4:
        dataset = payload.get("loadForecast")
        if (
            not isinstance(dataset, dict)
            or not dataset.get("ValueColumns")
            or not dataset.get("ValueRows")
        ):
            raise ValueError("APG cache loadForecast is missing or empty")

    return payload


def fetch_cache() -> dict:
    errors = []
    for url in cache_urls():
        try:
            payload = fetch_one(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"{url}: {exc}")
            print(f"WARNING: APG cache failed at {url}: {exc}", file=sys.stderr)
            continue

        age = int(datetime.now(timezone.utc).timestamp() - payload["fetchedAtEpoch"])
        print(
            f"APG cache: source={url}, schema={payload['schemaVersion']}, "
            f"{age // 60} min old, region={payload.get('region')}, "
            f"rows generation/load/borders/forecast="
            f"{len(payload['generation']['ValueRows'])}/"
            f"{len(payload['load']['ValueRows'])}/"
            f"{len(payload['borders']['ValueRows'])}/"
            f"{len(payload['generationForecast']['ValueRows'])}"
            + (
                f"/{len(payload['loadForecast']['ValueRows'])}"
                if payload.get("loadForecast")
                else ""
            )
        )
        return payload

    raise RuntimeError("all APG cache endpoints failed: " + "; ".join(errors))


def main() -> None:
    try:
        cached = fetch_cache()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"WARNING: APG cache unavailable; keeping Energy-Charts data: {exc}",
              file=sys.stderr)
        return

    datasets = {
        "AGPT": cached["generation"],
        "AL": cached["load"],
        "CBPF": cached["borders"],
    }

    def cached_fetch_series(kind: str, _start, _end) -> dict:
        try:
            return datasets[kind]
        except KeyError as exc:
            raise ValueError(f"unsupported cached APG dataset {kind}") from exc

    overlay_apg.fetch_series = cached_fetch_series
    overlay_apg.main()


if __name__ == "__main__":
    main()
