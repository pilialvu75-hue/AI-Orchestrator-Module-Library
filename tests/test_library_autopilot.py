from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_autopilot import run  # noqa: E402


class LibraryAutopilotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "catalog").mkdir(parents=True)
        self._write(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "test-library",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-11T00:00:00Z",
                "assets": [],
            },
        )
        self._write(
            self.root / "catalog" / "needs.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-11T00:00:00Z",
                "items": [],
            },
        )
        self._write(
            self.root / "contracts" / "index.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-11T00:00:00Z",
                "contracts": [
                    {
                        "contract_id": "voice.stt.v1",
                        "contract_version": "1.0",
                        "status": "stable",
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

    def _asset(self, *, valid: bool) -> Path:
        base = self.root / "intake" / "voice.autopilot_stt" / "1.0.0"
        (base / "provenance").mkdir(parents=True)
        (base / "provenance" / "LICENSE").write_text("MIT\n", encoding="utf-8")
        source_commit = "0123456789abcdef0123456789abcdef01234567"

        if valid:
            self._write(
                base / "tests" / "report.json",
                {
                    "schema": "ai-orchestrator.library-test-report.v1",
                    "asset_id": "voice.autopilot_stt",
                    "version": "1.0.0",
                    "source_commit": source_commit,
                    "passed": True,
                    "validated_on": ["android"],
                },
            )
            self._write(
                base / "security" / "sbom.json",
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "components": [],
                },
            )
            sbom_sha256 = hashlib.sha256(
                (base / "security" / "sbom.json").read_bytes()
            ).hexdigest()
            self._write(
                base / "security" / "review.json",
                {
                    "schema": "ai-orchestrator.library-security-review.v1",
                    "asset_id": "voice.autopilot_stt",
                    "version": "1.0.0",
                    "source_commit": source_commit,
                    "reviewed": True,
                    "known_vulnerabilities": 0,
                    "sbom_sha256": sbom_sha256,
                },
            )

        self._write(
            base / "manifest.json",
            {
                "id": "voice.autopilot_stt",
                "name": "Autopilot STT",
                "version": "1.0.0",
                "kind": "integration_bundle",
                "status": "discovered",
                "description": "fixture",
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
                    "license": "MIT",
                    "license_file": "provenance/LICENSE",
                    "retrieved_at": "2026-09-11T00:00:00Z",
                },
                "validation": {
                    "score": 0.95 if valid else 0.2,
                    "tests_passed": valid,
                    "test_report": "tests/report.json" if valid else None,
                    "validated_at": "2026-09-11T01:00:00Z" if valid else None,
                    "validated_on": ["android"] if valid else [],
                },
                "security": {
                    "reviewed": valid,
                    "reviewed_at": "2026-09-11T01:30:00Z" if valid else None,
                    "known_vulnerabilities": 0,
                    "sbom": "security/sbom.json" if valid else None,
                    "review_report": "security/review.json" if valid else None,
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
                    "provides": [{
                        "capability_id": "voice.stt",
                        "contract_id": "voice.stt.v1",
                        "contract_version": "1.0",
                    }],
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
            },
        )
        return base

    def test_valid_discovered_intake_reaches_certified_catalog(self) -> None:
        self._asset(valid=True)
        report = run(self.root)
        self.assertEqual(1, report["promoted"])
        module = self.root / "modules" / "voice.autopilot_stt" / "1.0.0" / "manifest.json"
        self.assertTrue(module.is_file())
        manifest = json.loads(module.read_text(encoding="utf-8"))
        self.assertEqual("certified", manifest["status"])
        catalog = json.loads((self.root / "catalog" / "index.json").read_text())
        self.assertEqual(1, len(catalog["assets"]))
        self.assertTrue((self.root / "catalog" / "offline-snapshot.json").is_file())
        package_index = json.loads((self.root / "packages" / "index.json").read_text())
        self.assertEqual(1, len(package_index["packages"]))

    def test_failed_gate_restores_exact_intake_and_does_not_certify(self) -> None:
        base = self._asset(valid=False)
        before = (base / "manifest.json").read_bytes()
        report = run(self.root)
        self.assertEqual(1, report["blocked"])
        self.assertEqual(before, (base / "manifest.json").read_bytes())
        self.assertFalse(
            (self.root / "modules" / "voice.autopilot_stt" / "1.0.0").exists()
        )
        catalog = json.loads((self.root / "catalog" / "index.json").read_text())
        self.assertEqual([], catalog["assets"])
        self.assertTrue((self.root / "catalog" / "offline-snapshot.json").is_file())
        package_index = json.loads((self.root / "packages" / "index.json").read_text())
        self.assertEqual([], package_index["packages"])

    def test_claimed_success_without_evidence_is_blocked(self) -> None:
        base = self._asset(valid=True)
        (base / "tests" / "report.json").unlink()
        before = (base / "manifest.json").read_bytes()
        report = run(self.root)
        self.assertEqual(1, report["blocked"])
        self.assertIn("validation.test_report does not exist", report["results"][0]["reason"])
        self.assertEqual(before, (base / "manifest.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
