#!/usr/bin/env python3
"""Build an experimental near-real-time Austrian generation nowcast.

This does NOT replace official APG data. It writes site/nowcast.json so the
model can be observed and backtested first.

v0 model:
- anchor on the newest complete APG generation-per-type row;
- wind follows APG's current wind forecast, corrected by the latest observed
  forecast error, with the correction decaying over a two-hour half-life;
- solar feed-in follows APG's solar feed-in forecast, calibrated by the latest
  actual/forecast ratio (bounded to avoid wild corrections);
- all other generation groups use persistence from the latest official row.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import overlay_apg
from run_apg_cache_overlay import fetch_cache

OUT = Path(__file__).resolve().parent.parent / "site" / "nowcast.json"
HALF_LIFE_SECONDS = 2 * 60 * 60
MAX_HORIZON_SECONDS = 3 * 60 * 60


def latest_at_or_before(series: dict[int, dict[str, float | None]], stamp: int,
                        max_gap: int | None = None) -> tuple[int, dict[str, float | None]] | None:
    candidates = [t for t in series if t <= stamp]
    if not candidates:
        return None
    t = max(candidates)
    if max_gap is not None and stamp - t > max_gap:
        return None
    return t, series[t]


def actual_groups(row: dict[str, float | None]) -> dict[str, float] | None:
    solar_key = next((key for key in ("SolarFeedIn", "B16", "SolarTotal")
                      if key in row), None)
    if solar_key is None:
        return None
    required = {
        "B01", "B04", "B05", "B06", "B09", "B10", "B11", "B12",
        "B15", "B17", "B19", "B20", solar_key,
    }
    if any(row.get(key) is None for key in required):
        return None
    return {
        "hydro": float(row["B11"]) + float(row["B12"]),
        "fossil": float(row["B04"]) + float(row["B05"]) + float(row["B06"]),
        "wind": float(row["B19"]),
        "pumped": float(row["B10"]),
        "biomass": float(row["B01"]) + float(row["B17"]),
        "other": float(row["B09"]) + float(row["B15"]) + float(row["B20"]),
        "solar": float(row[solar_key]),
    }


def forecast_value(row: dict[str, float | None], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return float(value)
    return None


def decay(seconds: int) -> float:
    return math.exp(-math.log(2) * max(seconds, 0) / HALF_LIFE_SECONDS)


def rounded_model(groups: dict[str, float]) -> dict:
    rounded = {key: round(value, 1) for key, value in groups.items()}
    return {"generationMw": round(sum(rounded.values()), 1), "groups": rounded}


def build_nowcast(cached: dict) -> dict:
    if cached.get("schemaVersion") != 3:
        raise ValueError("generation forecast requires APG cache schema 3")
    forecast_payload = cached.get("generationForecast")
    if not isinstance(forecast_payload, dict):
        raise ValueError("APG cache has no generationForecast dataset")

    actual = overlay_apg.parse(cached["generation"])
    forecast = overlay_apg.parse(forecast_payload)
    if not actual or not forecast:
        raise ValueError("APG actual or forecast series is empty")

    anchor: tuple[int, dict[str, float | None], dict[str, float]] | None = None
    for stamp in sorted(actual, reverse=True):
        groups = actual_groups(actual[stamp])
        if groups is not None:
            anchor = (stamp, actual[stamp], groups)
            break
    if anchor is None:
        raise ValueError("no complete official APG generation row")

    anchor_at, actual_row, anchor_groups = anchor
    anchor_forecast = latest_at_or_before(forecast, anchor_at, max_gap=60 * 60)
    if anchor_forecast is None:
        raise ValueError("no APG generation forecast near latest official generation row")
    anchor_forecast_at, forecast_anchor_row = anchor_forecast

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    quarter_now = now_epoch - now_epoch % (15 * 60)
    target = latest_at_or_before(forecast, quarter_now, max_gap=60 * 60)
    if target is None:
        raise ValueError("no current APG generation forecast row")
    target_at, forecast_target_row = target

    horizon = target_at - anchor_at
    if horizon < 0:
        raise ValueError("forecast target predates official anchor")
    if horizon > MAX_HORIZON_SECONDS:
        raise ValueError(f"official generation anchor is too old for nowcast ({horizon // 60} min)")
    weight = decay(horizon)

    persistence_groups = dict(anchor_groups)
    raw_groups = dict(anchor_groups)
    corrected_groups = dict(anchor_groups)

    wind_anchor_fc = forecast_value(forecast_anchor_row, "DAFWG")
    wind_target_fc = forecast_value(forecast_target_row, "DAFWG")
    if wind_anchor_fc is None or wind_target_fc is None:
        raise ValueError("APG forecast is missing wind")
    wind_bias = anchor_groups["wind"] - wind_anchor_fc
    raw_groups["wind"] = max(0.0, wind_target_fc)
    corrected_groups["wind"] = max(0.0, wind_target_fc + wind_bias * weight)

    solar_anchor_fc = forecast_value(
        forecast_anchor_row, "DAFSGFeedIn", "DAFSG", "DAFSGTotal")
    solar_target_fc = forecast_value(
        forecast_target_row, "DAFSGFeedIn", "DAFSG", "DAFSGTotal")
    if solar_anchor_fc is None or solar_target_fc is None:
        raise ValueError("APG forecast is missing solar")
    raw_groups["solar"] = max(0.0, solar_target_fc)
    if solar_anchor_fc >= 25:
        ratio = max(0.5, min(1.5, anchor_groups["solar"] / solar_anchor_fc))
        corrected_ratio = 1.0 + (ratio - 1.0) * weight
        corrected_groups["solar"] = max(0.0, solar_target_fc * corrected_ratio)
        solar_correction = {"mode": "ratio", "anchorRatio": round(ratio, 4)}
    else:
        solar_bias = anchor_groups["solar"] - solar_anchor_fc
        corrected_groups["solar"] = max(0.0, solar_target_fc + solar_bias * weight)
        solar_correction = {"mode": "additive", "anchorBiasMw": round(solar_bias, 1)}

    models = {
        "persistence": rounded_model(persistence_groups),
        "rawForecast": rounded_model(raw_groups),
        "corrected": rounded_model(corrected_groups),
    }
    corrected = models["corrected"]
    return {
        "schemaVersion": 2,
        "experimental": True,
        "model": "apg-forecast-bias-v0",
        "generatedAt": now_epoch,
        "anchorAt": anchor_at,
        "anchorForecastAt": anchor_forecast_at,
        "targetAt": target_at,
        "horizonMinutes": horizon // 60,
        "correctionWeight": round(weight, 4),
        "generationMw": corrected["generationMw"],
        "groups": corrected["groups"],
        "models": models,
        "diagnostics": {
            "wind": {
                "actualAnchorMw": round(float(actual_row["B19"]), 1),
                "forecastAnchorMw": round(wind_anchor_fc, 1),
                "forecastTargetMw": round(wind_target_fc, 1),
                "anchorBiasMw": round(wind_bias, 1),
            },
            "solar": {
                "actualAnchorMw": round(anchor_groups["solar"], 1),
                "forecastAnchorMw": round(solar_anchor_fc, 1),
                "forecastTargetMw": round(solar_target_fc, 1),
                **solar_correction,
            },
        },
        "notes": [
            "Wind and solar are model estimates; other generation groups use persistence from the latest official APG row.",
            "Persistence and raw-forecast baselines are included for point-in-time backtesting.",
            "This file is experimental and is not used as the site's official current generation value.",
        ],
    }


def main() -> None:
    try:
        cached = fetch_cache()
        nowcast = build_nowcast(cached)
    except Exception as exc:
        print(f"WARNING: generation nowcast unavailable: {exc}", file=sys.stderr)
        return
    OUT.write_text(json.dumps(nowcast, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print(
        f"generation nowcast: target {nowcast['horizonMinutes']} min after official anchor; "
        f"{nowcast['generationMw']:.0f} MW total, "
        f"wind {nowcast['groups']['wind']:.0f} MW, solar {nowcast['groups']['solar']:.0f} MW"
    )


if __name__ == "__main__":
    main()
