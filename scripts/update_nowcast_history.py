#!/usr/bin/env python3
"""Persist point-in-time nowcasts and score them once APG actuals arrive."""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import overlay_apg
from build_generation_nowcast import actual_groups
from run_apg_cache_overlay import fetch_cache

ROOT = Path(__file__).resolve().parent.parent
NOWCAST = ROOT / "site" / "nowcast.json"
OUT = ROOT / "site" / "nowcast-history.json"
HISTORY_URL = os.environ.get(
    "NOWCAST_HISTORY_URL",
    "https://rfuzzo.github.io/woher-kommt-der-strom/nowcast-history.json",
)
MAX_PREDICTIONS = 14 * 24 * 4
MODELS = ("persistence", "rawForecast", "corrected")
METRICS = ("generationMw", "wind", "solar")


def empty_history() -> dict:
    return {
        "schemaVersion": 1,
        "updatedAt": 0,
        "predictions": [],
        "summary": {"scoredCount": 0, "pendingCount": 0, "mae": {}},
    }


def load_previous() -> dict:
    sep = "&" if "?" in HISTORY_URL else "?"
    url = f"{HISTORY_URL}{sep}t={int(time.time())}"
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.load(response)
        if payload.get("schemaVersion") == 1 and isinstance(payload.get("predictions"), list):
            return payload
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            json.JSONDecodeError, ValueError):
        pass
    return empty_history()


def compact_model(model: dict) -> dict:
    groups = model["groups"]
    return {
        "generationMw": round(float(model["generationMw"]), 1),
        "wind": round(float(groups["wind"]), 1),
        "solar": round(float(groups["solar"]), 1),
    }


def prediction_from_nowcast(nowcast: dict) -> dict:
    return {
        "targetAt": int(nowcast["targetAt"]),
        "generatedAt": int(nowcast["generatedAt"]),
        "anchorAt": int(nowcast["anchorAt"]),
        "horizonMinutes": int(nowcast["horizonMinutes"]),
        "models": {name: compact_model(nowcast["models"][name]) for name in MODELS},
    }


def score_pending(history: dict, cached: dict) -> int:
    actual_series = overlay_apg.parse(cached["generation"])
    newly_scored = 0
    now = int(datetime.now(timezone.utc).timestamp())
    for prediction in history["predictions"]:
        if prediction.get("actual") is not None:
            continue
        target = int(prediction["targetAt"])
        row = actual_series.get(target)
        if row is None:
            continue
        groups = actual_groups(row)
        if groups is None:
            continue
        actual = {
            "generationMw": round(sum(groups.values()), 1),
            "wind": round(groups["wind"], 1),
            "solar": round(groups["solar"], 1),
        }
        errors = {}
        for model_name in MODELS:
            model = prediction["models"][model_name]
            errors[model_name] = {
                metric: round(float(model[metric]) - actual[metric], 1)
                for metric in METRICS
            }
        prediction["actual"] = actual
        prediction["errors"] = errors
        prediction["scoredAt"] = now
        newly_scored += 1
    return newly_scored


def summarize(history: dict) -> dict:
    scored = [p for p in history["predictions"] if p.get("actual") is not None]
    pending = len(history["predictions"]) - len(scored)
    mae: dict[str, dict[str, float | None]] = {}
    rmse: dict[str, dict[str, float | None]] = {}
    bias: dict[str, dict[str, float | None]] = {}
    for model_name in MODELS:
        mae[model_name], rmse[model_name], bias[model_name] = {}, {}, {}
        for metric in METRICS:
            values = [float(p["errors"][model_name][metric]) for p in scored]
            if values:
                mae[model_name][metric] = round(sum(abs(v) for v in values) / len(values), 1)
                rmse[model_name][metric] = round(math.sqrt(sum(v * v for v in values) / len(values)), 1)
                bias[model_name][metric] = round(sum(values) / len(values), 1)
            else:
                mae[model_name][metric] = None
                rmse[model_name][metric] = None
                bias[model_name][metric] = None
    return {
        "scoredCount": len(scored),
        "pendingCount": pending,
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
    }


def main() -> None:
    if not NOWCAST.exists():
        print("WARNING: no site/nowcast.json to archive", file=sys.stderr)
        return
    try:
        nowcast = json.loads(NOWCAST.read_text(encoding="utf-8"))
        if nowcast.get("schemaVersion") != 2 or not isinstance(nowcast.get("models"), dict):
            raise ValueError("nowcast does not contain backtest baselines")
        cached = fetch_cache()
    except Exception as exc:
        print(f"WARNING: nowcast history unavailable: {exc}", file=sys.stderr)
        return

    history = load_previous()
    prediction = prediction_from_nowcast(nowcast)
    existing = {int(p["targetAt"]) for p in history["predictions"]}
    added = False
    if prediction["targetAt"] not in existing:
        history["predictions"].append(prediction)
        added = True

    history["predictions"].sort(key=lambda p: int(p["targetAt"]))
    if len(history["predictions"]) > MAX_PREDICTIONS:
        history["predictions"] = history["predictions"][-MAX_PREDICTIONS:]

    newly_scored = score_pending(history, cached)
    history["updatedAt"] = int(datetime.now(timezone.utc).timestamp())
    history["summary"] = summarize(history)
    OUT.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")

    summary = history["summary"]
    print(
        f"nowcast history: {'added' if added else 'kept'} target {prediction['targetAt']}; "
        f"scored {newly_scored} newly, {summary['scoredCount']} total, "
        f"{summary['pendingCount']} pending"
    )
    if summary["scoredCount"]:
        print(
            "nowcast MAE MW (total/wind/solar): "
            + "; ".join(
                f"{model}="
                f"{summary['mae'][model]['generationMw']}/"
                f"{summary['mae'][model]['wind']}/"
                f"{summary['mae'][model]['solar']}"
                for model in MODELS
            )
        )


if __name__ == "__main__":
    main()
