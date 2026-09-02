import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest.mock import patch

import run_apg_cache_overlay


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def valid_payload() -> dict:
    dataset = {
        "ValueColumns": [{"InternalName": "x"}],
        "ValueRows": [{"V": [{"V": 1}]}],
    }
    return {
        "schemaVersion": 3,
        "fetchedAtEpoch": int(datetime.now(timezone.utc).timestamp()),
        "region": "test-fallback",
        "generation": dataset,
        "load": dataset,
        "borders": dataset,
        "generationForecast": dataset,
    }


class ApgCacheFallbackTests(unittest.TestCase):
    def test_uses_second_endpoint_when_primary_fails(self):
        encoded = json.dumps(valid_payload()).encode()
        responses = [urllib.error.URLError("primary down"), FakeResponse(encoded)]

        def open_next(*_args, **_kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        with patch.object(
            run_apg_cache_overlay,
            "cache_urls",
            return_value=("https://primary.invalid", "https://fallback.invalid"),
        ), \
             patch.object(run_apg_cache_overlay.urllib.request, "urlopen", side_effect=open_next):
            payload = run_apg_cache_overlay.fetch_cache()

        self.assertEqual(payload["region"], "test-fallback")
        self.assertEqual(responses, [])


if __name__ == "__main__":
    unittest.main()
