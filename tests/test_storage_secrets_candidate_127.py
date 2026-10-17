from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_pipeline import (  # noqa: E402
    AssetRef,
    PipelineError,
    promote,
    transition_intake,
    validate_normalization_gates,
)


ASSET = "storage.secrets.researcher.flutter_secure_storage"
VERSION = "0.1.0"
COMMIT = "e8eeb449cd512b26153f0a3376dfe374dd39a999"
SOURCE = ROOT / "intake" / ASSET / VERSION


class StorageSecretsCandidate127Tests(unittest.TestCase):
    @staticmethod
    def manifest() -> dict:
        return json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))

    def test_pinned_identity_and_contract_without_false_certification(self) -> None:
        manifest = self.manifest()
        self.assertEqual(manifest["id"], ASSET)
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(manifest["status"], "discovered")
        self.assertEqual(manifest["capabilities"], ["storage.secrets"])
        self.assertEqual(
            manifest["provenance"]["source_commit"], COMMIT
        )
        self.assertEqual(manifest["payload"]["upstream_commit"], COMMIT)
        self.assertEqual(manifest["provenance"]["license"], "BSD-3-Clause")
        self.assertEqual(
            manifest["connector"]["provides"][0],
            {
                "capability_id": "storage.secrets",
                "contract_id": "storage.secrets.v1",
                "contract_version": "1.0",
            },
        )
        self.assertFalse(manifest["validation"]["tests_passed"])
        self.assertEqual(manifest["validation"]["validated_on"], [])
        self.assertFalse(manifest["security"]["reviewed"])

    def test_preserves_license_and_upstream_source_evidence(self) -> None:
        manifest = self.manifest()
        license_path = SOURCE / manifest["provenance"]["license_file"]
        self.assertTrue(license_path.is_file())
        original = license_path.read_text(encoding="utf-8")
        self.assertIn("BSD 3-Clause License", original)
        self.assertIn("Copyright 2017 German Saprykin", original)
        evidence = json.loads(
            (SOURCE / "provenance" / "preflight-proof.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["source"]["commit_sha"], COMMIT)
        self.assertEqual(evidence["source"]["upstream_package_version"], "11.2.0")
        self.assertEqual(evidence["evidence"]["static_security"], "CLEAR")
        self.assertEqual(evidence["evidence"]["vulnerability_report"], "CLEAR")
        self.assertFalse(evidence["restrictions"]["library_certified"])

    def test_migration_gate_inventory_covers_existing_secret_consumers(self) -> None:
        gates = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        self.assertEqual(gates["schema"], "ai-orchestrator.library-secret-storage-migration-gates.v1")
        self.assertEqual(gates["source_app"]["resolved_version"], "10.3.4")
        self.assertEqual(gates["source_app"]["declared_constraint"], "^10.3.1")
        self.assertEqual(gates["candidate"]["package_version"], "11.2.0")
        self.assertEqual(gates["source_app"]["android_min_sdk"], 28)
        consumers = gates["secret_consumer_inventory"]
        self.assertEqual(
            {item["consumer"] for item in consumers},
            {
                "cloud_credentials",
                "workshop_github_auth",
                "module_library_github_config",
                "diagnostics_github_token",
            },
        )
        self.assertTrue(all(item["state"] == "PENDING_MIGRATION_VALIDATION" for item in consumers))
        self.assertTrue(all(item["source_path"].startswith("lib/") for item in consumers))

    def test_major_upgrade_is_fail_closed_without_migration_proofs(self) -> None:
        manifest = self.manifest()
        gates = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        self.assertFalse(gates["source_control"]["merge_allowed"])
        self.assertFalse(gates["source_control"]["certification_allowed"])
        self.assertFalse(gates["candidate"]["library_certified"])
        self.assertEqual(gates["source_control"]["stage"], "discovered")
        expected = {
            "verify_initial_secret_presence",
            "preupgrade_cipher_migration",
            "non_destructive_restore",
            "biometric_and_keychain_errors",
            "upgrade_rollback",
            "android_physical_gate",
            "desktop_platform_gates",
            "library_contract_and_security_review",
        }
        self.assertEqual({item["id"] for item in gates["acceptance_gates"]}, expected)
        self.assertTrue(all(item["state"] == "PENDING" for item in gates["acceptance_gates"]))
        self.assertFalse(manifest["validation"]["tests_passed"])
        self.assertFalse(manifest["security"]["reviewed"])
        self.assertEqual(manifest["integration"]["estimated_effort"], "high")
        self.assertIn("major-version-migration", manifest["tags"])

    def test_normalization_structure_is_valid_without_changing_stage(self) -> None:
        validate_normalization_gates(self.manifest(), SOURCE)
        self.assertEqual(self.manifest()["status"], "discovered")

    def test_stage_transitions_and_promotion_fail_closed_without_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy = root / "intake" / ASSET / VERSION
            copy.parent.mkdir(parents=True)
            shutil.copytree(SOURCE, copy)
            (root / "catalog").mkdir()
            (root / "catalog" / "index.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "library_id": "test-intake",
                        "catalog_version": "0.0.1",
                        "updated_at": None,
                        "assets": [],
                    }
                ),
                encoding="utf-8",
            )
            ref = AssetRef(ASSET, VERSION)
            self.assertEqual(
                transition_intake(root, ref, "quarantined")["status"],
                "quarantined",
            )
            self.assertEqual(
                transition_intake(root, ref, "normalized")["status"],
                "normalized",
            )
            with self.assertRaisesRegex(PipelineError, "tests_passed"):
                transition_intake(root, ref, "tested")
            with self.assertRaisesRegex(PipelineError, "only tested"):
                promote(root, ref, dry_run=True)
            self.assertFalse((root / "modules" / ASSET / VERSION).exists())
            self.assertEqual(
                json.loads((root / "catalog" / "index.json").read_text())["assets"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
