"""Typed external logging security request is never an authorization."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from external_dart_logging_typed_review import build_review_request, ExternalReviewError  # noqa: E402

BASE = Path("intake/diagnostics.logging.dartlang.logging_adapter")


class TypedExternalReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        destination = self.root / BASE
        destination.mkdir(parents=True)
        for version in ("0.1.0", "0.1.1"):
            shutil.copytree(ROOT / BASE / version, destination / version)
        self.current = destination / "0.1.1"

    def test_source_bound_unsigned_review_request(self):
        original_manifest = (self.current / "manifest.json").read_bytes()
        packet = build_review_request(self.root)
        self.assertEqual(packet, build_review_request(self.root))
        self.assertEqual("INDEPENDENT_REVIEW_REQUIRED", packet["status"])
        self.assertEqual("tested", packet["module_status"])
        self.assertEqual(18, packet["source"]["file_count"])
        self.assertEqual("2eaa1c85c6d116936bbfa461bd37173aa6ea6b3d841d58c2905ee421f39e0fab",
                         packet["source"]["combined_payload_sha256"])
        self.assertEqual(40929969173, packet["functional_testing"]["test_claim_ci_run_id"])
        self.assertEqual("CycloneDX", packet["dependency_inventory"]["cyclonedx_sbom"]["bomFormat"])
        self.assertFalse(packet["dependency_inventory"]["live_vulnerability_scan_completed"])
        self.assertFalse(packet["independent_security_reviewed"])
        self.assertFalse(packet["reviewer_signature_present"])
        self.assertFalse(packet["production_approved"])
        self.assertFalse(packet["certification_authorized"])
        self.assertEqual(original_manifest, (self.current / "manifest.json").read_bytes())

    def test_event_vocabulary_mitigation_is_not_called_certification(self):
        packet = build_review_request(self.root)
        findings = {item["finding"]: item for item in packet["findings"]}
        self.assertEqual("MITIGATED_IN_SOURCE_PENDING_INDEPENDENT_REVIEW",
                         findings["FREE_FORM_EVENT_CODE_API"]["state"])
        self.assertEqual("REQUIRES_REVIEW",
                         findings["GLOBAL_LOGGER_AVAILABLE_IN_ORIGINAL_UPSTREAM"]["state"])
        self.assertFalse(packet["security_certified"])

    def test_mutating_typed_adapter_or_original_vendor_fails_closed(self):
        adapter = self.current / "payload/src/lib/aivexus_external_logging.dart"
        adapter.write_text(adapter.read_text() + "\n// unexpected edit\n")
        with self.assertRaises(ExternalReviewError):
            build_review_request(self.root)
        shutil.copyfile(ROOT / BASE / "0.1.1/payload/src/lib/aivexus_external_logging.dart", adapter)
        upstream = self.current / "payload/src/vendor/logging/lib/src/logger.dart"
        upstream.write_text(upstream.read_text() + "\n// unexpected edit\n")
        with self.assertRaises(ExternalReviewError):
            build_review_request(self.root)

    def test_wrong_license_and_false_independent_review_are_rejected(self):
        path = self.current / "provenance/LICENSE"
        path.write_text(path.read_text() + "\nspoof\n")
        with self.assertRaisesRegex(ExternalReviewError, "license"):
            build_review_request(self.root)
        shutil.copyfile(ROOT / BASE / "0.1.1/provenance/LICENSE", path)
        manifest_path = self.current / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["security"]["reviewed"] = True
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ExternalReviewError, "forged security"):
            build_review_request(self.root)

    def test_fake_ci_run_is_not_accepted(self):
        report = self.current / "tests/dart-linux-ci-report.json"
        fake = json.loads(report.read_text())
        fake["evidence"]["github_run_id"] = 1
        report.write_text(json.dumps(fake))
        with self.assertRaisesRegex(ExternalReviewError, "typed CI receipt"):
            build_review_request(self.root)


if __name__ == "__main__":
    unittest.main()
