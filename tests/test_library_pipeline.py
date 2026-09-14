from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_pipeline import AssetRef, PipelineError, promote, transition_intake  # noqa: E402


class LibraryPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "catalog").mkdir(parents=True)
        self.write_json(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "test-library",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-11T00:00:00Z",
                "assets": [],
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def make_asset(
        self,
        *,
        status: str = "discovered",
        license_name: str = "MIT",
        known_vulnerabilities: int = 0,
        tests_passed: bool = False,
        score: float = 0.0,
    ) -> AssetRef:
        ref = AssetRef("voice.test_stt", "1.0.0")
        base = self.root / "intake" / ref.asset_id / ref.version
        (base / "provenance").mkdir(parents=True)
        (base / "provenance" / "LICENSE").write_text("test license\n", encoding="utf-8")

        tested = tests_passed
        source_commit = "0123456789abcdef0123456789abcdef01234567"
        if tested:
            self.write_json(
                base / "tests" / "report.json",
                {
                    "schema": "ai-orchestrator.library-test-report.v1",
                    "asset_id": ref.asset_id,
                    "version": ref.version,
                    "source_commit": source_commit,
                    "passed": True,
                    "validated_on": ["android"],
                },
            )
            self.write_json(
                base / "security" / "sbom.json",
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "components": [],
                },
            )
            sbom = base / "security" / "sbom.json"
            sbom_sha256 = hashlib.sha256(sbom.read_bytes()).hexdigest()
            self.write_json(
                base / "security" / "review.json",
                {
                    "schema": "ai-orchestrator.library-security-review.v1",
                    "asset_id": ref.asset_id,
                    "version": ref.version,
                    "source_commit": source_commit,
                    "reviewed": True,
                    "known_vulnerabilities": known_vulnerabilities,
                    "sbom_sha256": sbom_sha256,
                },
            )

        manifest = {
            "id": ref.asset_id,
            "name": "Test STT",
            "version": ref.version,
            "kind": "integration_bundle",
            "status": status,
            "description": "Test reusable STT asset.",
            "capabilities": ["voice.stt"],
            "platforms": ["android"],
            "languages": ["dart"],
            "frameworks": ["flutter"],
            "entry_paths": [],
            "dependencies": [],
            "provenance": {
                "origin": "researcher",
                "source_repository": "https://github.com/example/project",
                "source_commit": source_commit,
                "source_tag": None,
                "source_project_id": None,
                "source_task_id": None,
                "license": license_name,
                "license_file": "provenance/LICENSE",
                "retrieved_at": "2026-09-11T00:00:00Z",
            },
            "validation": {
                "score": score,
                "tests_passed": tested,
                "test_report": "tests/report.json" if tested else None,
                "validated_at": "2026-09-11T01:00:00Z" if tested else None,
                "validated_on": ["android"] if tested else [],
            },
            "security": {
                "reviewed": tested,
                "reviewed_at": "2026-09-11T01:30:00Z" if tested else None,
                "known_vulnerabilities": known_vulnerabilities,
                "sbom": "security/sbom.json" if tested else None,
                "review_report": "security/review.json" if tested else None,
                "notes": None,
            },
            "integration": {
                "estimated_effort": "low",
                "adaptation_allowed": True,
                "known_constraints": [],
                "adapter_notes": None,
            },
            "connector": {
                "standard": "ai-orchestrator-lego",
                "standard_version": "1.0.0",
                "provides": [
                    {
                        "capability_id": "voice.stt",
                        "contract_id": "voice.stt.v1",
                        "contract_version": "1.0",
                    }
                ],
                "requires": [],
                "integration_mode": "adapter",
                "adapters": [],
                "configuration_schema": None,
                "healthcheck": None,
            },
            "payload": {
                "type": "upstream_reference",
                "path": None,
                "sha256": None,
                "upstream_repository": "https://github.com/example/project",
                "upstream_commit": source_commit,
            },
            "quality": {
                "reuse_count": 0,
                "successful_integrations": 0,
                "failed_integrations": 0,
                "last_used_at": None,
            },
            "deprecation": {"reason": None, "replacement": None},
        }
        self.write_json(base / "manifest.json", manifest)
        return ref

    def test_lifecycle_must_advance_one_state_at_a_time(self) -> None:
        ref = self.make_asset()
        with self.assertRaisesRegex(PipelineError, "invalid transition"):
            transition_intake(self.root, ref, "normalized")

        manifest = transition_intake(self.root, ref, "quarantined")
        self.assertEqual("quarantined", manifest["status"])
        manifest = transition_intake(self.root, ref, "normalized")
        self.assertEqual("normalized", manifest["status"])

    def test_tested_transition_requires_real_test_evidence(self) -> None:
        ref = self.make_asset(status="normalized")
        with self.assertRaisesRegex(PipelineError, "tests_passed"):
            transition_intake(self.root, ref, "tested")

    def test_tested_transition_rejects_missing_test_report(self) -> None:
        ref = self.make_asset(status="normalized", tests_passed=True, score=0.95)
        (self.root / "intake" / ref.asset_id / ref.version / "tests" / "report.json").unlink()
        with self.assertRaisesRegex(PipelineError, "validation.test_report does not exist"):
            transition_intake(self.root, ref, "tested")

    def test_certification_rejects_known_vulnerabilities(self) -> None:
        ref = self.make_asset(
            status="tested",
            tests_passed=True,
            score=0.95,
            known_vulnerabilities=1,
        )
        with self.assertRaisesRegex(PipelineError, "known vulnerabilities"):
            promote(self.root, ref)

    def test_certification_rejects_restricted_license_without_explicit_review(self) -> None:
        ref = self.make_asset(
            status="tested",
            tests_passed=True,
            score=0.95,
            license_name="AGPL-3.0-only",
        )
        with self.assertRaisesRegex(PipelineError, "copyleft"):
            promote(self.root, ref)

    def test_certification_rejects_tampered_sbom(self) -> None:
        ref = self.make_asset(status="tested", tests_passed=True, score=0.95)
        sbom = self.root / "intake" / ref.asset_id / ref.version / "security" / "sbom.json"
        sbom.write_text('{"tampered":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "SBOM digest"):
            promote(self.root, ref)

    def test_dry_run_does_not_mutate_repository(self) -> None:
        ref = self.make_asset(status="tested", tests_passed=True, score=0.95)
        result = promote(self.root, ref, dry_run=True)
        self.assertEqual("dry_run_ok", result["result"])
        self.assertTrue((self.root / "intake" / ref.asset_id / ref.version).exists())
        self.assertFalse((self.root / "modules" / ref.asset_id / ref.version).exists())
        catalog = json.loads((self.root / "catalog" / "index.json").read_text())
        self.assertEqual([], catalog["assets"])

    def test_promotion_is_atomic_enough_and_idempotent(self) -> None:
        ref = self.make_asset(status="tested", tests_passed=True, score=0.95)
        result = promote(self.root, ref)
        self.assertEqual("promoted", result["result"])

        intake = self.root / "intake" / ref.asset_id / ref.version
        module_manifest = self.root / "modules" / ref.asset_id / ref.version / "manifest.json"
        self.assertFalse(intake.exists())
        self.assertTrue(module_manifest.is_file())
        promoted = json.loads(module_manifest.read_text())
        self.assertEqual("certified", promoted["status"])

        catalog = json.loads((self.root / "catalog" / "index.json").read_text())
        self.assertEqual("1.0.1", catalog["catalog_version"])
        self.assertEqual(1, len(catalog["assets"]))
        self.assertEqual("voice.test_stt", catalog["assets"][0]["id"])

        again = promote(self.root, ref)
        self.assertEqual("already_promoted", again["result"])
        catalog_again = json.loads((self.root / "catalog" / "index.json").read_text())
        self.assertEqual(1, len(catalog_again["assets"]))
        self.assertEqual("1.0.1", catalog_again["catalog_version"])


if __name__ == "__main__":
    unittest.main()
