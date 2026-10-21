"""Fail-closed tests for real three-platform pinned Dart evidence admission."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import sys
from pathlib import Path

# The protected writer executes this test module in isolation, not only in
# the larger discover suite where unrelated tests might alter sys.path first.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from tools.library_privacy_preflight import CANDIDATE, security_preflight
from library_pipeline import PipelineError
from tools.library_privacy_multiplatform_admission import (
    ASSET_ID, CHECKS, PLATFORMS, RECEIPT_SCHEMA,
    PlatformAdmissionError, admit_multiplatform,
)

RUN = 39556595702
SHA = "f" * 40


class MultiPlatformAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / CANDIDATE
        self.candidate.parent.mkdir(parents=True)
        shutil.copytree(ROOT / CANDIDATE, self.candidate)
        self.manifest_path = self.candidate / "manifest.json"
        # The protected writer can update production to three-platform tested
        # at any time. Always start unit tests from a reproducible Linux-only
        # tested *sandbox*, not the mutable real manifest.
        cross_report = self.candidate / "tests/dart-cross-platform-ci-report.json"
        if cross_report.exists():
            cross_report.unlink()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        linux_report = json.loads(
            (self.candidate / "tests/dart-linux-ci-report.json").read_text(encoding="utf-8")
        )
        manifest["status"] = "tested"
        manifest["platforms"] = ["linux"]
        manifest["validation"]["tests_passed"] = True
        manifest["validation"]["validated_on"] = ["linux"]
        manifest["validation"]["test_report"] = "tests/dart-linux-ci-report.json"
        manifest["validation"]["validated_at"] = linux_report["validated_at"]
        self.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.artifacts = self.root / "downloaded-artifacts"
        self.artifacts.mkdir()
        self.preflight = security_preflight(self.root)
        for platform in PLATFORMS:
            directory = self.artifacts / f"privacy-adversarial-{platform}-{RUN}"
            directory.mkdir()
            self.write(directory / "privacy-preflight.json", self.preflight)
            self.write(directory / "privacy-target-evidence.json", {
                "schema": RECEIPT_SCHEMA,
                "asset_id": ASSET_ID,
                "version": "0.1.0",
                "payload_sha256": self.preflight["payload_tree_sha256"],
                "platform": platform,
                "workflow_sha": SHA,
                "run_id": RUN,
                "run_attempt": 1,
                "checked_source_files": self.preflight["source_files"],
                "checks": CHECKS,
                "deterministic_adversarial_cases": 4096,
                "passed": True,
                "security_reviewed": False,
                "license_verified": False,
                "runtime_certified": False,
                "vulnerability_scanned": False,
            })

    def write(self, path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def update_receipt(self, platform, key, value):
        path = self.artifacts / f"privacy-adversarial-{platform}-{RUN}" / "privacy-target-evidence.json"
        data = self.read(path)
        data[key] = value
        self.write(path, data)

    def admit(self):
        return admit_multiplatform(
            root=self.root, artifacts=self.artifacts,
            workflow_sha=SHA, run_id=RUN, run_attempt=1,
            accepted_at="2026-10-21T11:00:00+00:00",
        )

    def test_real_source_and_three_exact_platforms_advance_only_tested(self):
        result = self.admit()
        self.assertEqual(result["result"], "tested_multiplatform")
        manifest = self.read(self.manifest_path)
        self.assertEqual(manifest["status"], "tested")
        self.assertEqual(manifest["platforms"], list(PLATFORMS))
        self.assertEqual(manifest["validation"]["validated_on"], list(PLATFORMS))
        self.assertTrue(manifest["validation"]["tests_passed"])
        self.assertEqual(manifest["validation"]["score"], 0.8)
        self.assertIs(manifest["security"]["reviewed"], False)
        self.assertIsNone(manifest["provenance"]["license"])
        report = self.read(self.candidate / "tests/dart-cross-platform-ci-report.json")
        self.assertEqual(report["validated_on"], list(PLATFORMS))
        self.assertEqual(report["workflow_sha"], SHA)
        self.assertEqual(report["workflow_run_id"], RUN)
        self.assertEqual(set(report["platform_proofs"]), set(PLATFORMS))
        self.assertEqual(report["deterministic_adversarial_cases_per_platform"], 4096)
        self.assertIs(report["security_certified"], False)
        self.assertIs(report["license_verified"], False)
        self.assertIs(report["runtime_certified"], False)
        self.assertEqual(self.admit()["result"], "already_tested")

    def test_missing_or_extra_platform_rejected_without_manifest_write(self):
        before = self.manifest_path.read_bytes()
        shutil.rmtree(self.artifacts / f"privacy-adversarial-windows-{RUN}")
        with self.assertRaisesRegex(PlatformAdmissionError, "all three"):
            self.admit()
        self.assertEqual(self.manifest_path.read_bytes(), before)
        directory = self.artifacts / "unexpected"
        directory.mkdir()
        with self.assertRaisesRegex(PlatformAdmissionError, "all three"):
            self.admit()

    def test_forged_platform_receipts_rejected_without_any_status_change(self):
        cases = [
            ("windows", "run_id", RUN + 1),
            ("macos", "workflow_sha", "b" * 40),
            ("linux", "run_attempt", 2),
            ("windows", "payload_sha256", "b" * 64),
            ("macos", "passed", False),
            ("linux", "platform", "android"),
            ("windows", "checked_source_files", []),
            ("macos", "checks", ["echo pass"]),
            ("linux", "deterministic_adversarial_cases", 0),
            ("windows", "security_reviewed", True),
            ("macos", "runtime_certified", True),
            ("linux", "license_verified", True),
            ("windows", "vulnerability_scanned", True),
        ]
        before = self.manifest_path.read_bytes()
        for platform, key, replacement in cases:
            path = self.artifacts / f"privacy-adversarial-{platform}-{RUN}" / "privacy-target-evidence.json"
            original = self.read(path)
            self.update_receipt(platform, key, replacement)
            with self.subTest(platform=platform, key=key), self.assertRaisesRegex(
                PlatformAdmissionError, "mismatched"
            ):
                self.admit()
            self.assertEqual(self.manifest_path.read_bytes(), before)
            self.write(path, original)

    def test_preflight_mismatch_and_source_tamper_rejected(self):
        path = self.artifacts / f"privacy-adversarial-linux-{RUN}" / "privacy-preflight.json"
        report = self.read(path)
        self.write(path, {**report, "license_verified": True})
        with self.assertRaisesRegex(PlatformAdmissionError, "preflight differs"):
            self.admit()
        self.write(path, report)
        source = self.candidate / "payload/src/lib/privacy_diagnostic_events.dart"
        source.write_text(source.read_text(encoding="utf-8") + "\n// altered\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "SHA256 mismatch"):
            self.admit()
        self.assertFalse((self.candidate / "tests/dart-cross-platform-ci-report.json").exists())

    def test_unreviewed_security_and_undeclared_license_cannot_be_overridden(self):
        original = self.read(self.manifest_path)
        for mutated in [
            {**original, "security": {**original["security"], "reviewed": True}},
            {**original, "provenance": {**original["provenance"], "license": "MIT"}},
        ]:
            self.write(self.manifest_path, mutated)
            with self.assertRaises(PlatformAdmissionError):
                self.admit()
            self.write(self.manifest_path, original)

    def test_rejects_run_identity_and_untrusted_extra_artifact(self):
        for changed in (
            {"workflow_sha": "invalid", "run_id": RUN, "run_attempt": 1},
            {"workflow_sha": SHA, "run_id": True, "run_attempt": 1},
            {"workflow_sha": SHA, "run_id": RUN, "run_attempt": 0},
        ):
            with self.subTest(changed=changed), self.assertRaises(PlatformAdmissionError):
                admit_multiplatform(root=self.root, artifacts=self.artifacts, **changed)
        (self.artifacts / "an-extra-artifact").mkdir()
        with self.assertRaisesRegex(PlatformAdmissionError, "all three"):
            self.admit()


if __name__ == "__main__":
    unittest.main()
