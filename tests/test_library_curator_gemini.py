from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_curator import RESPONSE_SCHEMA  # noqa: E402
from library_curator_gemini import (  # noqa: E402
    DEFAULT_MODEL,
    GeminiCuratorProvider,
    GeminiProviderError,
)


class LibraryCuratorGeminiTest(unittest.TestCase):
    @staticmethod
    def request() -> dict:
        return {
            "schema": "ai-orchestrator.library-curator-request.v1",
            "request_id": "0123456789abcdef01234567",
            "task": "coverage",
            "capability_id": "storage.local_db",
            "policy": {
                "advisory_only": True,
                "core_is_authoritative": True,
                "provider_may_mutate_library": False,
                "provider_may_certify": False,
                "provider_may_revoke": False,
            },
            "context": {"needs": [], "assets": []},
            "context_sha256": "a" * 64,
        }

    @staticmethod
    def gemini_success(request_id: str) -> bytes:
        structured = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request_id,
            "recommendations": [],
        }
        return json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(structured)}]
                        }
                    }
                ]
            }
        ).encode("utf-8")

    def test_missing_key_is_rejected_before_network(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(GeminiProviderError, "GEMINI_API_KEY"):
                GeminiCuratorProvider(api_key="")

    def test_key_uses_header_and_never_url(self) -> None:
        captured = {}

        def transport(url, headers, body, timeout):
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["body"] = body
            captured["timeout"] = timeout
            return 200, self.gemini_success(self.request()["request_id"])

        provider = GeminiCuratorProvider(
            api_key="test-secret-key",
            transport=transport,
            sleeper=lambda _: None,
        )
        result = provider.advise(self.request())
        self.assertEqual(RESPONSE_SCHEMA, result["schema"])
        self.assertNotIn("test-secret-key", captured["url"])
        self.assertEqual("test-secret-key", captured["headers"]["x-goog-api-key"])
        self.assertIn(DEFAULT_MODEL, captured["url"])

        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("application/json", body["generationConfig"]["responseFormat"]["text"]["mimeType"])
        self.assertEqual(
            RESPONSE_SCHEMA,
            body["generationConfig"]["responseFormat"]["text"]["schema"]["properties"]["schema"]["enum"][0],
        )
        serialized_body = captured["body"].decode("utf-8")
        self.assertNotIn("test-secret-key", serialized_body)

    def test_timeout_retries_then_succeeds(self) -> None:
        calls = []
        sleeps = []

        def transport(url, headers, body, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise GeminiProviderError("Gemini request timed out")
            return 200, self.gemini_success(self.request()["request_id"])

        provider = GeminiCuratorProvider(
            api_key="key",
            max_retries=2,
            transport=transport,
            sleeper=sleeps.append,
        )
        result = provider.advise(self.request())
        self.assertEqual(RESPONSE_SCHEMA, result["schema"])
        self.assertEqual(2, len(calls))
        self.assertEqual([1.0], sleeps)

    def test_transient_status_retries_then_succeeds(self) -> None:
        calls = []
        sleeps = []

        def transport(url, headers, body, timeout):
            calls.append(url)
            if len(calls) < 3:
                return 503, b"temporary"
            return 200, self.gemini_success(self.request()["request_id"])

        provider = GeminiCuratorProvider(
            api_key="key",
            max_retries=2,
            transport=transport,
            sleeper=sleeps.append,
        )
        result = provider.advise(self.request())
        self.assertEqual(RESPONSE_SCHEMA, result["schema"])
        self.assertEqual(3, len(calls))
        self.assertEqual([1.0, 2.0], sleeps)

    def test_non_transient_error_fails_without_retry(self) -> None:
        calls = []

        def transport(url, headers, body, timeout):
            calls.append(url)
            return 400, b"bad request"

        provider = GeminiCuratorProvider(
            api_key="key",
            max_retries=2,
            transport=transport,
            sleeper=lambda _: None,
        )
        with self.assertRaisesRegex(GeminiProviderError, "HTTP 400"):
            provider.advise(self.request())
        self.assertEqual(1, len(calls))

    def test_invalid_structured_output_is_rejected(self) -> None:
        payload = json.dumps(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "not-json"}]}}
                ]
            }
        ).encode("utf-8")

        provider = GeminiCuratorProvider(
            api_key="key",
            transport=lambda *_: (200, payload),
            sleeper=lambda _: None,
        )
        with self.assertRaisesRegex(GeminiProviderError, "structured output"):
            provider.advise(self.request())

    def test_model_is_configurable_without_changing_contract(self) -> None:
        captured = {}

        def transport(url, headers, body, timeout):
            captured["url"] = url
            return 200, self.gemini_success(self.request()["request_id"])

        provider = GeminiCuratorProvider(
            api_key="key",
            model="gemini-3.7-flash",
            transport=transport,
            sleeper=lambda _: None,
        )
        provider.advise(self.request())
        self.assertEqual("gemini:gemini-3.7-flash", provider.name)
        self.assertIn("gemini-3.7-flash", captured["url"])


if __name__ == "__main__":
    unittest.main()
