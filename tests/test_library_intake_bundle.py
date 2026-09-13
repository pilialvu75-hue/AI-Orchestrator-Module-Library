from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_intake_bundle import (  # noqa: E402
    IntakeBundleError,
    materialize_bundle,
    verify_bundle_bytes,
)
from library_pipeline import AssetRef, transition_intake  # noqa: E402


class LibraryIntakeBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _encoded_file(path: str, content: bytes) -> dict:
        return {
            "path": path,
            "content_base64": base64.b64encode(content).decode("ascii"),
        }

    def _bundle(self, *, files: list[dict] | None = None, payload_path: str = "payload/library-intake-payload.json") -> tuple[bytes, str]:
        payload_document = {
            "schema": "ai-orchestrator.library-intake-payload.v1",
            "files": files
            or [
                self._encoded_file("lib/a.dart", b"a"),
                self._encoded_file("lib/z.dart", b"z"),
            ],
        }
        payload_json = json.dumps(payload_document, separators=(",", ":"), ensure_ascii=False)
        payload_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        manifest = {
            "id": "demo.asset",
            "name": "Demo asset",
            "version": "1.0.0",
            "kind": "module",
            "status": "discovered",
            "description": "Cross-repository intake bundle fixture.",
            "tags": [],
            "capabilities": ["demo.capability"],
            "platforms": ["android"],
            "languages": ["dart"],
            "frameworks": ["flutter"],
            "entry_paths": ["lib/a.dart"],
            "dependencies": [],
            "provenance": {
                "origin": "cantiere",
                "source_repository": None,
                "source_commit": None,
                "source_tag": None,
                "source_project_id": "project-1",
                "source_task_id": "task-1",
                "license": "MIT",
                "license_file": None,
                "retrieved_at": "2026-09-13T19:00:00Z",
            },
            "validation": {
                "score": 0.95,
                "tests_passed": True,
                "test_report": None,
                "validated_at": "2026-09-13T19:00:00Z",
                "validated_on": ["android"],
            },
            "security": {
                "reviewed": True,
                "reviewed_at": "2026-09-13T19:00:00Z",
                "known_vulnerabilities": 0,
                "sbom": None,
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
                        "capability_id": "demo.capability",
                        "contract_id": "demo.capability.v1",
                        "contract_version": "1.0",
                    }
                ],
                "requires": [],
                "integration_mode": "source_bundle",
                "configuration_schema": None,
                "healthcheck": {"type": "none", "path": None},
            },
            "payload": {
                "type": "archive",
                "path": payload_path,
                "sha256": payload_sha,
                "upstream_repository": None,
                "upstream_commit": None,
            },
        }
        bundle = {
            "schema": "ai-orchestrator.library-intake-bundle.v1",
            "pin": "demo.asset@1.0.0",
            "manifest_path": "intake/demo.asset/1.0.0/manifest.json",
            "payload_path": payload_path,
            "payload_sha256": payload_sha,
            "payload_json": payload_json,
            "manifest": manifest,
        }
        raw = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return raw, hashlib.sha256(raw).hexdigest()

    def test_materialized_bundle_advances_through_real_normalization_gate(self) -> None:
        raw, bundle_sha = self._bundle()
        verified = verify_bundle_bytes(raw, bundle_sha)
        destination = materialize_bundle(self.root, verified)

        self.assertEqual(destination, self.root / "intake" / "demo.asset" / "1.0.0")
        self.assertTrue((destination / "manifest.json").is_file())
        self.assertTrue((destination / "payload" / "library-intake-payload.json").is_file())

        ref = AssetRef("demo.asset", "1.0.0")
        quarantined = transition_intake(self.root, ref, "quarantined")
        self.assertEqual(quarantined["status"], "quarantined")
        normalized = transition_intake(self.root, ref, "normalized")
        self.assertEqual(normalized["status"], "normalized")

    def test_repeated_identical_materialization_is_idempotent(self) -> None:
        raw, bundle_sha = self._bundle()
        verified = verify_bundle_bytes(raw, bundle_sha)
        first = materialize_bundle(self.root, verified)
        second = materialize_bundle(self.root, verified)
        self.assertEqual(first, second)

    def test_divergent_existing_intake_is_never_overwritten(self) -> None:
        raw, bundle_sha = self._bundle()
        verified = verify_bundle_bytes(raw, bundle_sha)
        destination = materialize_bundle(self.root, verified)
        (destination / "payload" / "library-intake-payload.json").write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(IntakeBundleError, "divergent"):
            materialize_bundle(self.root, verified)

    def test_bundle_and_payload_integrity_fail_closed(self) -> None:
        raw, bundle_sha = self._bundle()
        with self.assertRaisesRegex(IntakeBundleError, "bundle sha256 mismatch"):
            verify_bundle_bytes(raw + b" ", bundle_sha)

        decoded = json.loads(raw.decode("utf-8"))
        decoded["payload_json"] += " "
        tampered = json.dumps(decoded, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        tampered_sha = hashlib.sha256(tampered).hexdigest()
        with self.assertRaisesRegex(IntakeBundleError, "canonical payload sha256 mismatch"):
            verify_bundle_bytes(tampered, tampered_sha)

    def test_unsafe_payload_paths_are_rejected(self) -> None:
        for unsafe in ("../escape.dart", ".git/config", "android/key.properties"):
            raw, bundle_sha = self._bundle(files=[self._encoded_file(unsafe, b"x")])
            with self.assertRaisesRegex(IntakeBundleError, "unsafe payload file path"):
                verify_bundle_bytes(raw, bundle_sha)

    def test_archive_path_cannot_escape_payload_directory(self) -> None:
        raw, bundle_sha = self._bundle(payload_path="outside.json")
        with self.assertRaisesRegex(IntakeBundleError, "below payload"):
            verify_bundle_bytes(raw, bundle_sha)


if __name__ == "__main__":
    unittest.main()
