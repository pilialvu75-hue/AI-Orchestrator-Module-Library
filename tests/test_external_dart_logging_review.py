"""External module preflight supplies evidence, NEVER self-approves safety."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from external_dart_logging_review import ExternalReviewError, build_request  # noqa: E402

BASE = Path("intake/diagnostics.logging.dartlang.logging_adapter/0.1.0")
SANDBOX = Path("sandbox/external_dart_logging")


class ExternalDartLoggingReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dart-logging-review-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = ROOT / BASE
        dest = self.root / BASE
        dest.parent.mkdir(parents=True)
        shutil.copytree(source, dest)
        sandbox = self.root / SANDBOX
        sandbox.parent.mkdir(parents=True)
        shutil.copytree(ROOT / SANDBOX, sandbox)
        self.base = dest

    def test_handoff_has_real_source_and_no_authority(self):
        before = (self.base / "manifest.json").read_bytes()
        packet = build_request(self.root)
        self.assertEqual(packet, build_request(self.root))
        self.assertEqual("INDEPENDENT_REVIEW_REQUIRED", packet["status"])
        self.assertEqual(18, packet["source"]["source_file_count"])
        self.assertEqual(13, packet["source"]["original_upstream_file_count"])
        self.assertEqual("pkg:pub/logging@1.3.0",
                         packet["dependency_inventory"]["package_dependencies"][0])
        self.assertEqual("CycloneDX",
                         packet["dependency_inventory"]["cyclonedx_sbom"]["bomFormat"])
        self.assertFalse(packet["dependency_inventory"]["live_vulnerability_scan_performed"])
        self.assertFalse(packet["independent_security_reviewed"])
        self.assertFalse(packet["license_approved_by_independent_reviewer"])
        self.assertFalse(packet["reviewer_signature_present"])
        self.assertFalse(packet["production_approved"])
        self.assertFalse(packet["certification_authorized"])
        self.assertEqual([], packet["functional_test_claims"]["platforms_verified_by_this_packet"])
        self.assertEqual(before, (self.base / "manifest.json").read_bytes())

    def test_privacy_gap_is_explicit_and_blocking(self):
        packet = build_request(self.root)
        findings = packet["risks_requiring_resolution"]
        codes = {entry["id"] for entry in findings}
        self.assertIn("INPUT_SYNTAX_IS_NOT_PRIVACY_ALLOWLIST", codes)
        self.assertIn("UPSTREAM_LOGGER_CAN_CREATE_GLOBAL_STATE_IF_USED_DIRECTLY", codes)
        self.assertTrue(any(entry["severity"] == "blocking" for entry in findings))
        self.assertTrue(all(entry["review_status"] == "OPEN" for entry in findings))

    def test_tampering_either_pinned_adapter_or_original_upstream_fails(self):
        dart = self.base / "payload/src/lib/aivexus_external_logging.dart"
        dart.write_text(dart.read_text() + "\n// unauthorized change\n")
        with self.assertRaises(ExternalReviewError):
            build_request(self.root)
        shutil.copyfile(ROOT / BASE / "payload/src/lib/aivexus_external_logging.dart", dart)
        original = self.base / "payload/src/vendor/logging/lib/src/logger.dart"
        original.write_text(original.read_text() + "\n// unauthorized upstream\n")
        with self.assertRaises(ExternalReviewError):
            build_request(self.root)

    def test_license_and_report_are_bound_not_inferred(self):
        path = self.base / "provenance/LICENSE"
        path.write_text(path.read_text() + "\nforgery\n")
        with self.assertRaisesRegex(ExternalReviewError, "license"):
            build_request(self.root)
        shutil.copyfile(ROOT / BASE / "provenance/LICENSE", path)
        receipt = self.base / "tests/dart-linux-ci-report.json"
        report = json.loads(receipt.read_text())
        report["evidence"]["github_run_id"] = 42
        receipt.write_text(json.dumps(report))
        with self.assertRaisesRegex(ExternalReviewError, "pinned Linux CI"):
            build_request(self.root)

    def test_source_side_symlink_and_manifest_claim_fail_closed(self):
        path = self.base / "payload/src/tool/self_test.dart"
        path.unlink()
        path.symlink_to(ROOT / BASE / "payload/src/tool/self_test.dart")
        with self.assertRaises(ExternalReviewError):
            build_request(self.root)
        path.unlink()
        shutil.copyfile(ROOT / BASE / "payload/src/tool/self_test.dart", path)
        manifest_file = self.base / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["security"]["reviewed"] = True
        manifest_file.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ExternalReviewError, "not a substitute"):
            build_request(self.root)


if __name__ == "__main__":
    unittest.main()
