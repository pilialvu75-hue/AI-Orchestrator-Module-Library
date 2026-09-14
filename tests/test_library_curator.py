from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_curator import (  # noqa: E402
    CuratorError,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    build_request,
    run_curator,
    verify_response,
)


class FakeProvider:
    def __init__(self, response_builder):
        self._response_builder = response_builder
        self.seen_request = None

    @property
    def name(self) -> str:
        return "fake"

    def advise(self, request):
        self.seen_request = request
        return self._response_builder(request)


class LibraryCuratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "test-library",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-14T00:00:00Z",
                "assets": [
                    {
                        "id": "storage.certified_db",
                        "version": "1.0.0",
                        "manifest": "modules/storage.certified_db/1.0.0/manifest.json",
                        "status": "certified",
                        "availability": "active",
                        "kind": "module",
                        "capabilities": ["storage.local_db"],
                        "platforms": ["android"],
                        "contracts": ["storage.local_db.v1"],
                    }
                ],
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
                        "title": "Local database",
                        "priority": "high",
                        "desired_candidates": 2,
                        "status": "needed",
                        "targets": ["android", "desktop"],
                    }
                ],
            },
        )
        self._write(
            self.root
            / "modules"
            / "storage.certified_db"
            / "1.0.0"
            / "manifest.json",
            self._manifest(
                asset_id="storage.certified_db",
                version="1.0.0",
                status="certified",
                tests_passed=True,
                reviewed=True,
            ),
        )
        self._write(
            self.root
            / "intake"
            / "storage.research_candidate"
            / "0.1.0"
            / "manifest.json",
            self._manifest(
                asset_id="storage.research_candidate",
                version="0.1.0",
                status="discovered",
                tests_passed=False,
                reviewed=False,
            ),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _manifest(
        *,
        asset_id: str,
        version: str,
        status: str,
        tests_passed: bool,
        reviewed: bool,
    ) -> dict:
        return {
            "id": asset_id,
            "name": asset_id,
            "version": version,
            "kind": "module",
            "status": status,
            "description": "Database candidate",
            "capabilities": ["storage.local_db"],
            "platforms": ["android", "desktop"],
            "provenance": {
                "origin": "researcher",
                "source_repository": "https://github.com/example/db",
                "source_commit": "0123456789abcdef0123456789abcdef01234567",
                "license": "MIT",
                "license_file": "provenance/LICENSE",
                "retrieved_at": "2026-09-14T00:00:00Z",
            },
            "validation": {
                "score": 0.95 if tests_passed else 0.2,
                "tests_passed": tests_passed,
                "test_report": "evidence/test-report.json",
                "validated_on": ["android"] if tests_passed else [],
            },
            "security": {
                "reviewed": reviewed,
                "known_vulnerabilities": 0,
                "sbom": "evidence/sbom.json",
                "notes": "internal review notes must not reach the provider",
            },
            "integration": {
                "estimated_effort": "low",
                "adaptation_allowed": True,
                "known_constraints": ["requires sqlite"],
                "adapter_notes": "internal adapter notes",
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
                "upstream_repository": "https://github.com/example/db",
                "upstream_commit": "0123456789abcdef0123456789abcdef01234567",
            },
        }

    @staticmethod
    def _ranking_factors(refs: list[str]) -> list[dict]:
        factors = []
        for index, ref in enumerate(refs):
            overall = max(0.0, 0.9 - index * 0.1)
            factors.append(
                {
                    "asset_ref": ref,
                    "semantic_fit": overall,
                    "target_fit": 0.9,
                    "contract_fit": 0.9,
                    "evidence_strength": 0.9 if "certified" in ref else 0.4,
                    "integration_fit": 0.8,
                    "overall": overall,
                    "rationale": "Observable fit from supplied Library metadata.",
                }
            )
        return factors

    @classmethod
    def _response(cls, request: dict, *, recommendation_type: str, refs: list[str]) -> dict:
        recommendation = {
            "type": recommendation_type,
            "confidence": 0.91,
            "summary": "Advisory result based only on supplied Library context.",
            "asset_refs": refs,
            "capability_ids": ["storage.local_db"],
            "adapter_suggestions": [],
            "warnings": [],
        }
        if recommendation_type == "candidate_ranking":
            recommendation["ranking_factors"] = cls._ranking_factors(refs)
        return {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [recommendation],
        }

    def test_request_is_deterministic_and_sanitized(self) -> None:
        first = build_request(
            self.root,
            task="rank_candidates",
            capability_id="storage.local_db",
        )
        second = build_request(
            self.root,
            task="rank_candidates",
            capability_id="storage.local_db",
        )
        self.assertEqual(first, second)
        self.assertEqual(REQUEST_SCHEMA, first["schema"])
        self.assertTrue(first["policy"]["advisory_only"])
        self.assertFalse(first["policy"]["provider_may_mutate_library"])

        rendered = json.dumps(first, sort_keys=True)
        self.assertNotIn("license_file", rendered)
        self.assertNotIn("test_report", rendered)
        self.assertNotIn("sbom.json", rendered)
        self.assertNotIn("internal review notes", rendered)
        self.assertNotIn("internal adapter notes", rendered)

        refs = [item["ref"] for item in first["context"]["assets"]]
        self.assertEqual(
            ["storage.certified_db@1.0.0", "storage.research_candidate@0.1.0"],
            refs,
        )

    def test_active_certified_reuse_recommendation_is_accepted(self) -> None:
        request = build_request(
            self.root,
            task="rank_candidates",
            capability_id="storage.local_db",
        )
        response = self._response(
            request,
            recommendation_type="reuse_recommendation",
            refs=["storage.certified_db@1.0.0"],
        )
        verified = verify_response(request, response)
        self.assertEqual("reuse_recommendation", verified["recommendations"][0]["type"])

    def test_uncertified_intake_can_be_ranked_but_never_recommended_for_reuse(self) -> None:
        request = build_request(
            self.root,
            task="rank_candidates",
            capability_id="storage.local_db",
        )
        ranking = self._response(
            request,
            recommendation_type="candidate_ranking",
            refs=["storage.research_candidate@0.1.0"],
        )
        self.assertEqual(
            "candidate_ranking",
            verify_response(request, ranking)["recommendations"][0]["type"],
        )

        reuse = self._response(
            request,
            recommendation_type="reuse_recommendation",
            refs=["storage.research_candidate@0.1.0"],
        )
        with self.assertRaisesRegex(CuratorError, "not an active certified"):
            verify_response(request, reuse)

    def test_unknown_asset_and_mutation_fields_fail_closed(self) -> None:
        request = build_request(
            self.root,
            task="coverage",
            capability_id="storage.local_db",
        )
        unknown = self._response(
            request,
            recommendation_type="candidate_ranking",
            refs=["storage.fake@9.9.9"],
        )
        with self.assertRaisesRegex(CuratorError, "unknown assets"):
            verify_response(request, unknown)

        mutation = self._response(
            request,
            recommendation_type="coverage_gap",
            refs=[],
        )
        mutation["mutate_catalog"] = True
        with self.assertRaisesRegex(CuratorError, "unsupported fields"):
            verify_response(request, mutation)

    def test_ranking_order_must_match_non_increasing_overall_score(self) -> None:
        request = build_request(
            self.root,
            task="rank_candidates",
            capability_id="storage.local_db",
        )
        response = self._response(
            request,
            recommendation_type="candidate_ranking",
            refs=["storage.certified_db@1.0.0", "storage.research_candidate@0.1.0"],
        )
        factors = response["recommendations"][0]["ranking_factors"]
        factors[0]["overall"] = 0.4
        factors[1]["overall"] = 0.8
        with self.assertRaisesRegex(CuratorError, "non-increasing overall"):
            verify_response(request, response)

    def test_gateway_does_not_mutate_library(self) -> None:
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        provider = FakeProvider(
            lambda request: self._response(
                request,
                recommendation_type="candidate_ranking",
                refs=["storage.certified_db@1.0.0", "storage.research_candidate@0.1.0"],
            )
        )
        result = run_curator(
            self.root,
            provider,
            task="rank_candidates",
            capability_id="storage.local_db",
        )
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertEqual("fake", result["provider"])
        self.assertTrue(result["core_verification"]["passed"])
        self.assertFalse(result["core_verification"]["library_mutated"])
        self.assertIsNotNone(provider.seen_request)


if __name__ == "__main__":
    unittest.main()
