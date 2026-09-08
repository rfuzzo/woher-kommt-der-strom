#!/usr/bin/env python3
"""Unit tests for generation nowcast candidates and history migration."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import update_nowcast_history as history_module
from build_generation_nowcast import build_nowcast, reconcile_total
from update_nowcast_history import summarize


TZ = ZoneInfo("Europe/Vienna")


def apg_row(stamp: int, values: list[float]) -> dict:
    local = datetime.fromtimestamp(stamp, timezone.utc).astimezone(TZ)
    return {
        "DF": local.strftime("%d.%m.%Y"),
        "TF": local.strftime("%H:%M"),
        "V": [{"V": value} for value in values],
    }


def dataset(names: list[str], rows: list[dict]) -> dict:
    return {
        "ValueColumns": [{"InternalName": name} for name in names],
        "ValueRows": rows,
    }


class TotalTrendTests(unittest.TestCase):
    def test_reconcile_total_preserves_wind_solar_and_mix(self) -> None:
        groups = {
            "hydro": 2000.0,
            "fossil": 1000.0,
            "wind": 600.0,
            "pumped": 400.0,
            "biomass": 200.0,
            "other": 300.0,
            "solar": 500.0,
        }
        result = reconcile_total(groups, 6000.0)

        self.assertEqual(result["wind"], 600.0)
        self.assertEqual(result["solar"], 500.0)
        self.assertEqual(result["biomass"], 200.0)
        self.assertEqual(result["other"], 300.0)
        self.assertAlmostEqual(sum(result.values()), 6000.0)
        self.assertAlmostEqual(result["hydro"] / result["fossil"], 2.0)

    def test_reconcile_total_never_makes_other_generation_negative(self) -> None:
        groups = {
            "hydro": 100.0,
            "fossil": 100.0,
            "wind": 600.0,
            "pumped": 100.0,
            "biomass": 100.0,
            "other": 100.0,
            "solar": 500.0,
        }
        result = reconcile_total(groups, 900.0)

        self.assertAlmostEqual(sum(result.values()), 1300.0)
        self.assertTrue(all(value >= 0 for value in result.values()))

    def test_reconcile_total_preserves_negative_pumped_storage(self) -> None:
        groups = {
            "hydro": 1470.0,
            "fossil": 18.0,
            "wind": 623.1,
            "pumped": -1588.0,
            "biomass": 256.0,
            "other": 22.1,
            "solar": 3620.1,
        }
        result = reconcile_total(groups, 4961.3)

        self.assertEqual(result["pumped"], -1588.0)
        self.assertEqual(result["wind"], 623.1)
        self.assertEqual(result["solar"], 3620.1)
        self.assertAlmostEqual(sum(result.values()), 4961.3)
        self.assertLess(max(result.values()), 4000.0)

    def test_build_adds_total_forecast_change_to_anchor_actual(self) -> None:
        now = int(datetime.now(timezone.utc).timestamp())
        target = now - now % (15 * 60)
        anchor = target - 75 * 60
        actual_names = [
            "B01", "B04", "B05", "B06", "B09", "B10", "B11",
            "B12", "B15", "B17", "B19", "B20", "SolarFeedIn",
        ]
        actual_values = [200, 300, 200, 100, 50, 400, 1200, 800, 25, 100, 600, 25, 500]
        anchor_total = sum(actual_values)
        cached = {
            "schemaVersion": 4,
            "generation": dataset(actual_names, [apg_row(anchor, actual_values)]),
            "load": dataset(["AL"], [apg_row(anchor, [5000])]),
            "borders": dataset(["Sum"], [apg_row(anchor, [700])]),
            "generationForecast": dataset(
                ["DAFTG", "DAFWG", "DAFSG"],
                [
                    apg_row(anchor, [3000, 550, 450]),
                    apg_row(target, [3400, 650, 550]),
                ],
            ),
            "loadForecast": dataset(
                ["LF"],
                [apg_row(anchor, [4800]), apg_row(target, [5000])],
            ),
        }

        result = build_nowcast(cached)

        self.assertIn("totalTrend", result["models"])
        self.assertAlmostEqual(
            result["models"]["totalTrend"]["generationMw"],
            anchor_total + 400,
            delta=0.2,
        )
        self.assertEqual(result["diagnostics"]["total"]["forecastChangeMw"], 400.0)
        self.assertGreater(result["loadMw"], 5000.0)
        self.assertAlmostEqual(
            result["netImportMw"],
            700 + (result["loadMw"] - 5000) - 400,
            delta=0.2,
        )


class HistoryMigrationTests(unittest.TestCase):
    def test_legacy_predictions_do_not_count_as_total_trend_scores(self) -> None:
        history = {
            "predictions": [{
                "actual": {"generationMw": 100, "wind": 20, "solar": 10},
                "errors": {
                    "persistence": {"generationMw": 5, "wind": -2, "solar": 1},
                    "rawForecast": {"generationMw": 6, "wind": -1, "solar": 2},
                    "corrected": {"generationMw": 4, "wind": 0, "solar": 0},
                },
            }],
        }

        summary = summarize(history)

        self.assertEqual(summary["scoredCount"], 1)
        self.assertEqual(summary["modelScoredCount"]["corrected"], 1)
        self.assertEqual(summary["modelScoredCount"]["totalTrend"], 0)
        self.assertIsNone(summary["mae"]["totalTrend"]["generationMw"])

    def test_missing_nowcast_preserves_restored_history(self) -> None:
        history = {
            "schemaVersion": 1,
            "updatedAt": 123,
            "predictions": [{"targetAt": 100, "actual": None}],
            "summary": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "nowcast-history.json"
            out.write_text(json.dumps(history), encoding="utf-8")
            missing_nowcast = Path(directory) / "nowcast.json"
            with (
                mock.patch.object(history_module, "OUT", out),
                mock.patch.object(history_module, "NOWCAST", missing_nowcast),
            ):
                history_module.main()

            preserved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(preserved["updatedAt"], 123)
            self.assertEqual(len(preserved["predictions"]), 1)
            self.assertEqual(preserved["summary"]["pendingCount"], 1)


if __name__ == "__main__":
    unittest.main()
