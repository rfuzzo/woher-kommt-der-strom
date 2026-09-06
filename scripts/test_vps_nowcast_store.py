import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock


VPS_DIR = Path(__file__).parents[1] / "proxy" / "vps"
sys.path.insert(0, str(VPS_DIR))
import nowcast_store  # noqa: E402


def compact_models() -> dict:
    return {
        name: {"generationMw": 100.0, "wind": 20.0, "solar": 10.0}
        for name in nowcast_store.MODELS
    }


class VpsNowcastStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        nowcast_store.initialize(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_import_preserves_but_excludes_broken_total_trend(self):
        history = {
            "schemaVersion": 1,
            "predictions": [{
                "targetAt": 100,
                "generatedAt": 90,
                "anchorAt": 40,
                "horizonMinutes": 60,
                "models": compact_models(),
                "actual": {"generationMw": 90, "wind": 18, "solar": 9},
                "errors": {
                    name: {"generationMw": 10, "wind": 2, "solar": 1}
                    for name in nowcast_store.MODELS
                },
                "scoredAt": 200,
            }],
        }

        self.assertEqual(nowcast_store.import_history(self.connection, history), 1)
        exported = nowcast_store.export_history(self.connection, 300)
        prediction = exported["predictions"][0]
        self.assertIn(nowcast_store.BROKEN_LEGACY_MODEL, prediction["models"])
        self.assertNotIn("totalTrend", prediction["models"])
        self.assertEqual(exported["summary"]["modelScoredCount"]["corrected"], 1)
        self.assertEqual(exported["summary"]["modelScoredCount"]["totalTrend"], 0)

    def test_new_prediction_is_scored_for_all_current_models(self):
        nowcast = {
            "targetAt": 100,
            "generatedAt": 90,
            "anchorAt": 40,
            "horizonMinutes": 60,
            "model": "apg-forecast-bias-v1",
            "diagnostics": {"total": {"targetMw": 100}},
            "models": {
                name: {
                    "generationMw": 100,
                    "groups": {"wind": 20, "solar": 10},
                }
                for name in nowcast_store.MODELS
            },
        }
        actual_row = {
            "B01": 5.0, "B04": 10.0, "B05": 10.0, "B06": 10.0,
            "B09": 5.0, "B10": 0.0, "B11": 10.0, "B12": 10.0,
            "B15": 0.0, "B17": 5.0, "B19": 20.0, "B20": 0.0,
            "SolarFeedIn": 10.0,
        }
        self.assertTrue(nowcast_store.insert_prediction(self.connection, nowcast))
        with mock.patch.object(
            nowcast_store.overlay_apg, "parse", return_value={100: actual_row}
        ):
            self.assertEqual(
                nowcast_store.score_pending(self.connection, {"generation": {}}, 200), 1
            )
        exported = nowcast_store.export_history(self.connection, 300)
        self.assertEqual(exported["summary"]["scoredCount"], 1)
        self.assertEqual(exported["summary"]["modelScoredCount"]["totalTrend"], 1)
        self.assertEqual(exported["predictions"][0]["modelVersion"], "apg-forecast-bias-v1")


if __name__ == "__main__":
    unittest.main()
