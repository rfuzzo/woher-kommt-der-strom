#!/usr/bin/env python3
"""Unit tests for generation nowcast candidates and history migration."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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

        self.assertAlmostEqual(sum(result.values()), 1100.0)
        self.assertTrue(all(value >= 0 for value in result.values()))

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
            "schemaVersion": 3,
            "generation": dataset(actual_names, [apg_row(anchor, actual_values)]),
            "generationForecast": dataset(
                ["DAFTG", "DAFWG", "DAFSG"],
                [
                    apg_row(anchor, [3000, 550, 450]),
                    apg_row(target, [3400, 650, 550]),
                ],
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


if __name__ == "__main__":
    unittest.main()
