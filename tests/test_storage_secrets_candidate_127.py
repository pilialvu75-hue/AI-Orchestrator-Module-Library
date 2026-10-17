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
            "android_upgrade_status_pre_read",
            "android_backup_restore_isolation",
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

    def test_offline_migration_assessor_reports_all_pending_gates(self) -> None:
        import runpy

        assess = runpy.run_path(
            str(SOURCE / "tests" / "migration_readiness.py")
        )["assess"]
        evidence = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        report = assess(self.manifest(), evidence)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertEqual(len(report["pending_gates"]), 10)
        self.assertIn("MIGRATION_EVIDENCE_PENDING", report["blockers"])
        self.assertFalse(report["library_certified"])
        self.assertFalse(report["runtime_upgrade_authorized"])
        self.assertFalse(report["secrets_read"])

    def test_forged_pass_flags_cannot_grant_runtime_or_certification(self) -> None:
        import runpy

        assess = runpy.run_path(
            str(SOURCE / "tests" / "migration_readiness.py")
        )["assess"]
        evidence = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        for gate in evidence["acceptance_gates"]:
            gate["state"] = "PASS"
        missing_probe = assess(self.manifest(), evidence)
        self.assertEqual(missing_probe["state"], "BLOCKED")
        self.assertIn("ANDROID_UPGRADE_PROBE_NOT_CLEARED", missing_probe["blockers"])
        evidence["android_upgrade_probe"] = {
            "state": "ok",
            "reason": "none",
            "entry_count": 4,
            "will_discard_on_next_access": False,
            "performed_before_first_read": True,
            "device_receipt": "synthetic-not-an-attestation",
        }
        report = assess(self.manifest(), evidence)
        self.assertEqual(report["state"], "INDEPENDENT_REVIEW_REQUIRED")
        self.assertFalse(report["library_certified"])
        self.assertFalse(report["runtime_upgrade_authorized"])

    def test_upgrade_probe_rejects_unreadable_discarded_and_unsupported(self) -> None:
        import runpy

        classify = runpy.run_path(
            str(SOURCE / "tests" / "migration_readiness.py")
        )["classify_upgrade_probe"]
        baseline = {
            "state": "ok",
            "reason": "none",
            "entry_count": 3,
            "will_discard_on_next_access": False,
            "performed_before_first_read": True,
            "device_receipt": "synthetic-fixture",
        }
        self.assertEqual(classify(baseline), "SAFE_CANDIDATE_UNDER_REVIEW")
        for state, reason, verdict in (
            ("legacyDataUnreadable", "removedCipher", "LEGACY_DATA_AT_RISK"),
            ("legacyDataDiscarded", "missingKeyMaterial", "LEGACY_DATA_AT_RISK"),
            ("unknown", "authenticationRequired", "UNKNOWN_STATE"),
            ("ok", "unsupportedPlatform", "UNSUPPORTED_OR_UNEXPECTED"),
        ):
            with self.subTest(state=state, reason=reason):
                raw = dict(baseline, state=state, reason=reason)
                self.assertEqual(classify(raw), verdict)
        self.assertEqual(
            classify(dict(baseline, will_discard_on_next_access=True)),
            "POTENTIAL_DESTRUCTIVE_ACCESS",
        )
        self.assertEqual(
            classify(dict(baseline, performed_before_first_read=False)),
            "PRE_READ_ORDER_NOT_PROVEN",
        )
        self.assertEqual(
            classify(dict(baseline, device_receipt=None)),
            "DEVICE_RECEIPT_MISSING",
        )

    def test_backup_and_upgrade_gate_cannot_disappear_silently(self) -> None:
        import runpy

        assess = runpy.run_path(
            str(SOURCE / "tests" / "migration_readiness.py")
        )["assess"]
        evidence = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        evidence["acceptance_gates"] = [
            row for row in evidence["acceptance_gates"]
            if row["id"] != "android_backup_restore_isolation"
        ]
        report = assess(self.manifest(), evidence)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertIn("MIGRATION_GATES_INCOMPLETE", report["blockers"])
        self.assertIn("android_backup_restore_isolation", report["pending_gates"])

    def test_migration_assessor_rejects_pin_drift_and_fake_testing(self) -> None:
        import runpy

        assess = runpy.run_path(
            str(SOURCE / "tests" / "migration_readiness.py")
        )["assess"]
        evidence = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        bad = self.manifest()
        bad["provenance"]["source_commit"] = "0" * 40
        bad["validation"]["tests_passed"] = True
        bad["security"]["reviewed"] = True
        report = assess(bad, evidence)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertIn("SOURCE_COMMIT_MISMATCH", report["blockers"])
        self.assertIn("UNVERIFIED_TEST_CLAIM", report["blockers"])
        self.assertIn("UNVERIFIED_SECURITY_REVIEW_CLAIM", report["blockers"])

    def test_migration_assessor_detects_missing_credential_consumer(self) -> None:
        import runpy

        assess = runpy.run_path(
            str(SOURCE / "tests" / "migration_readiness.py")
        )["assess"]
        evidence = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        evidence["secret_consumer_inventory"].pop()
        report = assess(self.manifest(), evidence)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertIn(
            "CREDENTIAL_CONSUMER_INVENTORY_INCOMPLETE", report["blockers"]
        )

    def test_offline_checker_cli_emits_safe_machine_readable_block(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(SOURCE / "tests" / "migration_readiness.py"),
                "--manifest",
                str(SOURCE / "manifest.json"),
                "--evidence",
                str(SOURCE / "tests" / "migration-gates.json"),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertFalse(report["runtime_upgrade_authorized"])
        self.assertFalse(report["secrets_read"])
        self.assertEqual(len(report["pending_gates"]), 10)
        self.assertNotIn("token", result.stdout.lower())
        self.assertNotIn("password", result.stdout.lower())

    def test_merged_apk_manifest_triage_detects_implicit_backup_policy(self) -> None:
        import runpy

        audit = runpy.run_path(
            str(SOURCE / "tests" / "android_backup_manifest_audit.py")
        )["audit"]
        output = audit(
            "E: manifest (line=2)\n"
            "  E: application (line=25)\n"
            "    A: android:label(0x01010001)=\\\"Demo\\\"\n"
            "    E: activity (line=30)\n"
            "      A: android:allowBackup(0x01010280)=(type 0x12)0x0\n"
        )
        self.assertEqual(output["state"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(output["allow_backup"], "NOT_DECLARED")
        self.assertEqual(output["data_extraction_rules"], "NOT_DECLARED")
        self.assertIn("BACKUP_NOT_EXPLICITLY_DISABLED", output["reasons"])
        self.assertFalse(output["apk_identity_verified"])
        self.assertFalse(output["library_certified"])
        self.assertFalse(output["secret_material_examined"])

    def test_merged_apk_manifest_triage_never_certifies_even_with_references(self) -> None:
        import runpy

        audit = runpy.run_path(
            str(SOURCE / "tests" / "android_backup_manifest_audit.py")
        )["audit"]
        output = audit(
            "E: manifest (line=2)\n"
            "  E: application (line=25)\n"
            "    A: android:allowBackup(0x01010280)=(type 0x12)0x0\n"
            "    A: android:dataExtractionRules(0x01010695)=@0x7f100002\n"
            "    A: android:fullBackupContent(0x010104eb)=@0x7f100003\n"
        )
        self.assertEqual(output["allow_backup"], "EXPLICIT_FALSE")
        self.assertEqual(output["data_extraction_rules"], "REFERENCED")
        self.assertEqual(output["full_backup_content"], "REFERENCED")
        self.assertEqual(output["reasons"], [])
        self.assertEqual(output["state"], "EVIDENCE_INCOMPLETE")
        self.assertFalse(output["cloud_transfer_effective_policy_verified"])
        self.assertFalse(output["device_transfer_effective_policy_verified"])
        self.assertFalse(output["keystore_restore_fixture_tested"])

    def test_merged_apk_manifest_triage_flags_true_or_unreadable(self) -> None:
        import runpy

        audit = runpy.run_path(
            str(SOURCE / "tests" / "android_backup_manifest_audit.py")
        )["audit"]
        for option, state in (
            ("(type 0x12)0xffffffff", "EXPLICIT_TRUE"),
            ("(type 0x12)0x0", "EXPLICIT_FALSE"),
            ("@0x7f00", "UNKNOWN_VALUE"),
        ):
            with self.subTest(option=option):
                report = audit(
                    "E: manifest (line=1)\n"
                    "  E: application (line=2)\n"
                    f"    A: android:allowBackup(0x01010280)={option}\n"
                )
                self.assertEqual(report["allow_backup"], state)
                self.assertEqual(report["state"], "EVIDENCE_INCOMPLETE")
        with self.assertRaisesRegex(ValueError, "no application"):
            audit("E: manifest (line=1)\n")

    def test_apk_manifest_audit_cli_reports_only_backup_metadata(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic-aapt2.txt"
            path.write_text(
                "E: manifest (line=1)\n"
                "  E: application (line=2)\n"
                "    A: android:allowBackup(0x01010280)=(type 0x12)0xffffffff\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SOURCE / "tests" / "android_backup_manifest_audit.py"),
                    "--aapt2-xmltree",
                    str(path),
                ],
                check=True, capture_output=True, text=True, timeout=15,
            )
        report = json.loads(result.stdout)
        self.assertEqual(report["allow_backup"], "EXPLICIT_TRUE")
        self.assertFalse(report["app_change_authorized"])
        self.assertNotIn("token", result.stdout.lower())
        self.assertNotIn("secret value", result.stdout.lower())

    def test_real_published_apk_proof_is_pinned_but_not_device_accepted(self) -> None:
        import re

        path = SOURCE / "provenance" / "published-apk-manifest-proof.json"
        proof = json.loads(path.read_text(encoding="utf-8"))
        source = proof["source"]
        observed = proof["evidence"]
        self.assertEqual(source["release_tag"], "v1.0.12+3204")
        self.assertEqual(source["asset_id"], 643772718)
        self.assertEqual(source["size_bytes"], 167959098)
        self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(observed["sha256_and_size_checked"])
        self.assertTrue(observed["merged_manifest_observed"])
        for name in (
            "allow_backup", "data_extraction_rules", "full_backup_content"
        ):
            self.assertEqual(observed[name], "NOT_DECLARED")
        self.assertEqual(proof["restrictions"]["acceptance_state"], "EVIDENCE_INCOMPLETE")
        for flag in (
            "physical_backup_restore_tested",
            "cloud_backup_policy_verified",
            "device_to_device_transfer_policy_verified",
            "signing_identity_verified",
            "library_certified",
            "apk_upgrade_authorized",
            "secret_material_examined",
        ):
            self.assertFalse(proof["restrictions"][flag])
        gates = json.loads(
            (SOURCE / "tests" / "migration-gates.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            next(item for item in gates["acceptance_gates"]
                 if item["id"] == "android_backup_restore_isolation")["state"],
            "PENDING",
        )

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
