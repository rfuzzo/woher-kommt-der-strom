import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "proxy" / "vps" / "apg_cache.py"
SPEC = importlib.util.spec_from_file_location("vps_apg_cache", MODULE_PATH)
assert SPEC and SPEC.loader
apg_cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apg_cache)


class VpsApgCacheTests(unittest.TestCase):
    def test_unwraps_response_data(self):
        result = apg_cache.unwrap({
            "ResponseData": {
                "ValueColumns": [{"InternalName": "x"}],
                "ValueRows": [{"V": [{"V": 1}]}],
            }
        })
        self.assertEqual(result["ValueColumns"][0]["InternalName"], "x")
        self.assertEqual(len(result["ValueRows"]), 1)

    def test_merge_rejects_changed_columns(self):
        first = {"ValueColumns": [{"InternalName": "x"}], "ValueRows": []}
        second = {"ValueColumns": [{"InternalName": "y"}], "ValueRows": []}
        with self.assertRaisesRegex(ValueError, "ValueColumns changed"):
            apg_cache.merge_days(first, second)

    def test_atomic_write_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            output.write_text('{"old":true}\n', encoding="utf-8")
            apg_cache.atomic_write_json(output, {"schemaVersion": 4})
            self.assertEqual(json.loads(output.read_text()), {"schemaVersion": 4})
            self.assertFalse((Path(directory) / ".latest.json.tmp").exists())

    def test_load_forecast_uses_dalf_product_path(self):
        response = {
            "ValueColumns": [{"InternalName": "LF"}],
            "ValueRows": [],
        }
        yesterday = date(2026, 9, 7)
        today = date(2026, 9, 8)
        tomorrow = date(2026, 9, 9)
        with mock.patch.object(apg_cache, "fetch_json", return_value=response) as fetch:
            apg_cache.fetch_kind("ALF", yesterday, today, tomorrow, "DALF")

        self.assertEqual(fetch.call_count, 2)
        self.assertIn("/ALF/Data/DALF/English/PT15M/", fetch.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
