from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_curator import CuratorError, RESPONSE_SCHEMA  # noqa: E402
from library_curator_semantic import run_semantic_ranking  # noqa: E402


class FakeProvider:
    def __init__(self, builder):
        self.builder = builder
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake-semantic"

    def advise(self, request):
        self.calls += 1
        return self.builder(request)


class LibraryCuratorSemanticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "semantic-test-library",
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
                        "capability_id": "storage.local_db",
                        "title": "Local database / persistence",
                        "priority": "high",
                        "desired_candidates": 2,
                        "status": "needed",
                        "targets": ["android", "desktop"],
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

    def _add_intake(self, asset_id: str, version: str, *, score: float) -> str:
        manifest = {
            "id": asset_id,
            "name": asset_id,
            "version": version,
            "kind": "module",
            "status": "discovered",
            "description": "Reusable local database candidate.",
            "capabilities": ["storage.local_db"],
            "platforms": ["android", "desktop"],
            "provenance": {
                "origin": "researcher",
                "source_repository": f"https://github.com/example/{asset_id}",
                "source_commit": "0123456789abcdef0123456789abcdef01234567",
                "license": "MIT",
                "license_file": "provenance/LICENSE",
            },
            "validation": {
                "score": score,
                "tests_passed": False,
                "validated_on": [],
            },
            "security": {
                "reviewed": False,
                "known_vulnerabilities": 0,
            },
            "integration": {
                "estimated_effort": "low",
                "adaptation_allowed": True,
                "known_constraints": [],
            },
            "connector": {
                "standard": "ai-orchestrator-lego",
                "standard_version": "1.0.0",
                "provides": [
                    {
                        "capability_id": "storage.local_db",
                        "contract_id": "storage.local_db.v1",
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
        }
        self._write(
            self.root / "intake" / asset_id / version / "manifest.json",
            manifest,
        )
        return f"{asset_id}@{version}"

    @staticmethod
    def _factor(ref: str, overall: float) -> dict:
        return {
            "asset_ref": ref,
            "semantic_fit": overall,
            "target_fit": 0.9,
            "contract_fit": 0.9,
            "evidence_strength": 0.4,
            "integration_fit": 0.8,
            "overall": overall,
            "rationale": "Matches the requested capability and declared targets.",
        }

    @classmethod
    def _ranking_response(cls, request: dict, refs: list[str]) -> dict:
        scores = [max(0.0, 0.9 - index * 0.1) for index in range(len(refs))]
        return {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [
                {
                    "type": "candidate_ranking",
                    "confidence": 0.9,
                    "summary": "Candidates ranked from strongest to weakest advisory fit.",
                    "asset_refs": refs,
                    "capability_ids": ["storage.local_db"],
                    "adapter_suggestions": [],
                    "warnings": ["Intake candidates are not certified for reuse."],
                    "ranking_factors": [
                        cls._factor(ref, score)
                        for ref, score in zip(refs, scores)
                    ],
                }
            ],
        }

    def test_no_candidates_skips_ai_and_returns_deterministic_gap(self) -> None:
        provider = FakeProvider(lambda request: self._ranking_response(request, []))
        result = run_semantic_ranking(
            self.root,
            provider,
            capability_id="storage.local_db",
        )
        self.assertEqual(0, provider.calls)
        self.assertFalse(result["core_verification"]["ai_called"])
        self.assertEqual(0, result["core_verification"]["candidate_count"])
        self.assertEqual(
            "deterministic-core:no-candidates",
            result["provider"],
        )
        recommendation = result["advice"]["recommendations"][0]
        self.assertEqual("coverage_gap", recommendation["type"])
        self.assertEqual([], recommendation["asset_refs"])

    def test_all_candidates_are_ranked_once(self) -> None:
        first = self._add_intake("storage.alpha", "0.1.0", score=0.2)
        second = self._add_intake("storage.beta", "0.2.0", score=0.3)
        refs = sorted([first, second])
        provider = FakeProvider(lambda request: self._ranking_response(request, refs))

        result = run_semantic_ranking(
            self.root,
            provider,
            capability_id="storage.local_db",
        )
        self.assertEqual(1, provider.calls)
        self.assertTrue(result["core_verification"]["ai_called"])
        self.assertEqual(2, result["core_verification"]["candidate_count"])
        ranking = result["advice"]["recommendations"][0]
        self.assertEqual(refs, ranking["asset_refs"])
        self.assertEqual(
            refs,
            [factor["asset_ref"] for factor in ranking["ranking_factors"]],
        )

    def test_incomplete_candidate_ranking_fails_closed(self) -> None:
        first = self._add_intake("storage.alpha", "0.1.0", score=0.2)
        self._add_intake("storage.beta", "0.2.0", score=0.3)
        provider = FakeProvider(
            lambda request: self._ranking_response(request, [first])
        )

        with self.assertRaisesRegex(CuratorError, "cover every supplied candidate"):
            run_semantic_ranking(
                self.root,
                provider,
                capability_id="storage.local_db",
            )

    def test_semantic_ranking_never_mutates_library(self) -> None:
        ref = self._add_intake("storage.alpha", "0.1.0", score=0.2)
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        provider = FakeProvider(
            lambda request: self._ranking_response(request, [ref])
        )
        run_semantic_ranking(
            self.root,
            provider,
            capability_id="storage.local_db",
        )
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
