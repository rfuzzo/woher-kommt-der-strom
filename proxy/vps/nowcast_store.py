#!/usr/bin/env python3
"""Collect and score APG nowcasts in a durable SQLite database."""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import overlay_apg
from apg_cache import atomic_write_json
from build_generation_nowcast import actual_groups, build_nowcast


CACHE = Path(os.environ.get("APG_CACHE_OUTPUT", "/var/lib/apg-cache/latest.json"))
DATABASE = Path(os.environ.get("NOWCAST_DATABASE", "/var/lib/apg-cache/nowcasts.sqlite3"))
CURRENT_OUT = Path(os.environ.get("NOWCAST_OUTPUT", "/var/lib/apg-cache/nowcast.json"))
HISTORY_OUT = Path(
    os.environ.get("NOWCAST_HISTORY_OUTPUT", "/var/lib/apg-cache/nowcast-history.json")
)
MODELS = ("persistence", "rawForecast", "corrected", "totalTrend")
METRICS = ("generationMw", "wind", "solar")
BROKEN_LEGACY_MODEL = "totalTrendV0Broken"


def initialize(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            target_at INTEGER PRIMARY KEY,
            generated_at INTEGER NOT NULL,
            anchor_at INTEGER NOT NULL,
            horizon_minutes INTEGER NOT NULL,
            model_version TEXT NOT NULL,
            models_json TEXT NOT NULL,
            diagnostics_json TEXT,
            actual_json TEXT,
            errors_json TEXT,
            scored_at INTEGER
        )
        """
    )


def compact_model(model: dict) -> dict:
    groups = model["groups"]
    return {
        "generationMw": round(float(model["generationMw"]), 1),
        "wind": round(float(groups["wind"]), 1),
        "solar": round(float(groups["solar"]), 1),
    }


def insert_prediction(connection: sqlite3.Connection, nowcast: dict) -> bool:
    models = {
        name: compact_model(nowcast["models"][name])
        for name in MODELS
        if name in nowcast["models"]
    }
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO predictions (
            target_at, generated_at, anchor_at, horizon_minutes, model_version,
            models_json, diagnostics_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(nowcast["targetAt"]),
            int(nowcast["generatedAt"]),
            int(nowcast["anchorAt"]),
            int(nowcast["horizonMinutes"]),
            str(nowcast.get("model", "unknown")),
            json.dumps(models, separators=(",", ":")),
            json.dumps(nowcast.get("diagnostics", {}), separators=(",", ":")),
        ),
    )
    return cursor.rowcount == 1


def import_history(connection: sqlite3.Connection, history: dict) -> int:
    """Seed SQLite while excluding known-broken legacy totalTrend scores."""
    if history.get("schemaVersion") != 1 or not isinstance(history.get("predictions"), list):
        raise ValueError("unsupported nowcast history seed")
    imported = 0
    for prediction in history["predictions"]:
        models = dict(prediction.get("models", {}))
        errors = dict(prediction.get("errors", {}))
        if "totalTrend" in models:
            models[BROKEN_LEGACY_MODEL] = models.pop("totalTrend")
        if "totalTrend" in errors:
            errors[BROKEN_LEGACY_MODEL] = errors.pop("totalTrend")
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO predictions (
                target_at, generated_at, anchor_at, horizon_minutes, model_version,
                models_json, diagnostics_json, actual_json, errors_json, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(prediction["targetAt"]),
                int(prediction["generatedAt"]),
                int(prediction["anchorAt"]),
                int(prediction["horizonMinutes"]),
                str(prediction.get("modelVersion", "legacy-pages")),
                json.dumps(models, separators=(",", ":")),
                json.dumps(prediction.get("diagnostics", {}), separators=(",", ":")),
                json.dumps(prediction["actual"], separators=(",", ":"))
                if prediction.get("actual") is not None
                else None,
                json.dumps(errors, separators=(",", ":")) if errors else None,
                int(prediction["scoredAt"]) if prediction.get("scoredAt") else None,
            ),
        )
        imported += cursor.rowcount
    return imported


def score_pending(
    connection: sqlite3.Connection, cached: dict, scored_at: int | None = None
) -> int:
    actual_series = overlay_apg.parse(cached["generation"])
    scored_at = scored_at or int(datetime.now(timezone.utc).timestamp())
    newly_scored = 0
    pending = connection.execute(
        "SELECT target_at, models_json FROM predictions WHERE actual_json IS NULL"
    ).fetchall()
    for target_at, models_json in pending:
        row = actual_series.get(int(target_at))
        groups = actual_groups(row) if row is not None else None
        if groups is None:
            continue
        actual = {
            "generationMw": round(sum(groups.values()), 1),
            "wind": round(groups["wind"], 1),
            "solar": round(groups["solar"], 1),
        }
        models = json.loads(models_json)
        errors = {
            name: {
                metric: round(float(model[metric]) - actual[metric], 1)
                for metric in METRICS
            }
            for name, model in models.items()
        }
        connection.execute(
            """
            UPDATE predictions
            SET actual_json = ?, errors_json = ?, scored_at = ?
            WHERE target_at = ?
            """,
            (
                json.dumps(actual, separators=(",", ":")),
                json.dumps(errors, separators=(",", ":")),
                scored_at,
                target_at,
            ),
        )
        newly_scored += 1
    return newly_scored


def summarize(predictions: list[dict]) -> dict:
    scored = [prediction for prediction in predictions if prediction.get("actual") is not None]
    result = {
        "scoredCount": len(scored),
        "pendingCount": len(predictions) - len(scored),
        "modelScoredCount": {},
        "mae": {},
        "rmse": {},
        "bias": {},
    }
    for model_name in MODELS:
        result["mae"][model_name] = {}
        result["rmse"][model_name] = {}
        result["bias"][model_name] = {}
        result["modelScoredCount"][model_name] = sum(
            model_name in prediction.get("errors", {}) for prediction in scored
        )
        for metric in METRICS:
            values = [
                float(prediction["errors"][model_name][metric])
                for prediction in scored
                if metric in prediction.get("errors", {}).get(model_name, {})
            ]
            result["mae"][model_name][metric] = (
                round(sum(abs(value) for value in values) / len(values), 1) if values else None
            )
            result["rmse"][model_name][metric] = (
                round(math.sqrt(sum(value * value for value in values) / len(values)), 1)
                if values
                else None
            )
            result["bias"][model_name][metric] = (
                round(sum(values) / len(values), 1) if values else None
            )
    return result


def export_history(connection: sqlite3.Connection, updated_at: int) -> dict:
    predictions = []
    rows = connection.execute(
        """
        SELECT target_at, generated_at, anchor_at, horizon_minutes, model_version,
               models_json, diagnostics_json, actual_json, errors_json, scored_at
        FROM predictions ORDER BY target_at
        """
    ).fetchall()
    for row in rows:
        prediction = {
            "targetAt": row[0],
            "generatedAt": row[1],
            "anchorAt": row[2],
            "horizonMinutes": row[3],
            "modelVersion": row[4],
            "models": json.loads(row[5]),
            "diagnostics": json.loads(row[6]) if row[6] else {},
        }
        if row[7] is not None:
            prediction["actual"] = json.loads(row[7])
            prediction["errors"] = json.loads(row[8])
            prediction["scoredAt"] = row[9]
        predictions.append(prediction)
    return {
        "schemaVersion": 1,
        "updatedAt": updated_at,
        "predictions": predictions,
        "summary": summarize(predictions),
    }


def collect(seed: Path | None = None) -> dict:
    cached = json.loads(CACHE.read_text(encoding="utf-8"))
    nowcast = build_nowcast(cached)
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as connection:
        initialize(connection)
        imported = 0
        if seed is not None:
            imported = import_history(connection, json.loads(seed.read_text(encoding="utf-8")))
        added = insert_prediction(connection, nowcast)
        scored = score_pending(connection, cached, int(nowcast["generatedAt"]))
        connection.commit()
        history = export_history(connection, int(nowcast["generatedAt"]))

    atomic_write_json(CURRENT_OUT, nowcast)
    atomic_write_json(HISTORY_OUT, history)
    summary = history["summary"]
    print(
        f"nowcast SQLite: imported {imported}, {'added' if added else 'kept'} "
        f"target {nowcast['targetAt']}; scored {scored} newly, "
        f"{summary['scoredCount']} total, {summary['pendingCount']} pending"
    )
    return history


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-history", type=Path)
    args = parser.parse_args()
    collect(args.import_history)


if __name__ == "__main__":
    main()
