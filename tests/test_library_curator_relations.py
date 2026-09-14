from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_curator import CuratorError, RESPONSE_SCHEMA  # noqa: E402
from library_curator_relations import (  # noqa: E402
    run_adapter_analysis,
    run_duplicate_analysis,
)


class FakeProvider:
    def __init__(self, builder):
        self.builder = builder
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake-relations"

    def advise(self, request):
        self.calls += 1
        return self.builder(request)


class LibraryCuratorRelationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "relations-test-library",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-14T00:00:00Z",
                "assets": [],
            },
        )
        self._write(
            self.root / "catalog" / "needs.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-14T00:00:00Z",
                "items": [
                    {
                        "capability_id": "network.http",
                        "title": "HTTP client",
                        "priority": "high",
                        "desired_candidates": 2,
                        "status": "needed",
                        "targets": ["android", "desktop", "web"],
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def _add(self, asset_id: str, version: str) -> str:
        self._write(
            self.root / "intake" / asset_id / version / "manifest.json",
            {
                "id": asset_id,
                "name": asset_id,
                "version": version,
                "kind": "module",
                "status": "discovered",
                "description": "HTTP client with retries and cancellation.",
                "capabilities": ["network.http"],
                "platforms": ["android", "desktop", "web"],
                "provenance": {
                    "origin": "researcher",
                    "source_repository": f"https://github.com/example/{asset_id}",
                    "source_commit": "0123456789abcdef0123456789abcdef01234567",
                    "license": "MIT",
                    "license_file": "provenance/LICENSE",
                },
                "validation": {"score": 0.2, "tests_passed": False, "validated_on": []},
                "security": {"reviewed": False, "known_vulnerabilities": 0},
                "integration": {
                    "estimated_effort": "low",
                    "adaptation_allowed": True,
                    "known_constraints": ["adapter required for cancellation token"],
                },
                "connector": {
                    "standard": "ai-orchestrator-lego",
                    "standard_version": "1.0.0",
                    "provides": [
                        {
                            "capability_id": "network.http",
                            "contract_id": "network.http.v1",
                            "contract_version": "1.0",
                        }
                    ],
                    "requires": [],
                    "integration_mode": "adapter",
                },
                "payload": {
                    "type": "upstream_reference",
                    "upstream_repository": f"https://github.com/example/{asset_id}",
                    "upstream_commit": "0123456789abcdef0123456789abcdef01234567",
                },
            },
        )
        return f"{asset_id}@{version}"

    @staticmethod
    def _response(request: dict, recommendation: dict) -> dict:
        return {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [recommendation],
        }

    def test_duplicate_analysis_skips_ai_with_fewer_than_two_candidates(self) -> None:
        ref = self._add("network.alpha", "0.1.0")
        provider = FakeProvider(lambda request: {})
        result = run_duplicate_analysis(
            self.root,
            provider,
            capability_id="network.http",
        )
        self.assertEqual(0, provider.calls)
        self.assertFalse(result["core_verification"]["ai_called"])
        self.assertEqual([ref], result["core_verification"]["alternative_candidate_refs"])
        self.assertEqual([], result["advice"]["recommendations"])

    def test_duplicate_hint_must_cite_at_least_two_candidates(self) -> None:
        first = self._add("network.alpha", "0.1.0")
        self._add("network.beta", "0.2.0")
        provider = FakeProvider(
            lambda request: self._response(
                request,
                {
                    "type": "duplicate_hint",
                    "confidence": 0.8,
                    "summary": "Possible near duplicate.",
                    "asset_refs": [first],
                    "capability_ids": ["network.http"],
                    "adapter_suggestions": [],
                    "warnings": [],
                },
            )
        )
        with self.assertRaisesRegex(CuratorError, "at least two"):
            run_duplicate_analysis(
                self.root,
                provider,
                capability_id="network.http",
            )

    def test_duplicate_analysis_exposes_all_deterministic_alternatives(self) -> None:
        first = self._add("network.alpha", "0.1.0")
        second = self._add("network.beta", "0.2.0")
        refs = sorted([first, second])
        provider = FakeProvider(
            lambda request: self._response(
                request,
                {
                    "type": "duplicate_hint",
                    "confidence": 0.82,
                    "summary": "Both candidates expose highly overlapping HTTP behavior.",
                    "asset_refs": refs,
                    "capability_ids": ["network.http"],
                    "adapter_suggestions": [],
                    "warnings": ["This is advisory similarity only."],
                },
            )
        )
        result = run_duplicate_analysis(
            self.root,
            provider,
            capability_id="network.http",
        )
        self.assertEqual(1, provider.calls)
        self.assertEqual(refs, result["core_verification"]["alternative_candidate_refs"])
        self.assertEqual("duplicate_hint", result["advice"]["recommendations"][0]["type"])

    def test_adapter_hint_requires_asset_and_concrete_suggestion(self) -> None:
        ref = self._add("network.alpha", "0.1.0")
        provider = FakeProvider(
            lambda request: self._response(
                request,
                {
                    "type": "adapter_hint",
                    "confidence": 0.9,
                    "summary": "Cancellation semantics need an adapter.",
                    "asset_refs": [ref],
                    "capability_ids": ["network.http"],
                    "adapter_suggestions": [],
                    "warnings": [],
                },
            )
        )
        with self.assertRaisesRegex(CuratorError, "adapter_suggestions"):
            run_adapter_analysis(
                self.root,
                provider,
                capability_id="network.http",
            )

    def test_adapter_analysis_returns_verified_advice_without_mutation(self) -> None:
        ref = self._add("network.alpha", "0.1.0")
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        provider = FakeProvider(
            lambda request: self._response(
                request,
                {
                    "type": "adapter_hint",
                    "confidence": 0.9,
                    "summary": "Map the host cancellation token to the candidate API.",
                    "asset_refs": [ref],
                    "capability_ids": ["network.http"],
                    "adapter_suggestions": ["CancellationTokenAdapter"],
                    "warnings": [],
                },
            )
        )
        result = run_adapter_analysis(
            self.root,
            provider,
            capability_id="network.http",
        )
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertTrue(result["core_verification"]["ai_called"])
        self.assertEqual(
            ["CancellationTokenAdapter"],
            result["advice"]["recommendations"][0]["adapter_suggestions"],
        )


if __name__ == "__main__":
    unittest.main()
