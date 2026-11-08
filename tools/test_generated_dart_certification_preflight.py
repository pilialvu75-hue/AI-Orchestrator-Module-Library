import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from generated_dart_certification_preflight import inspect


class GeneratedDartCertificationPreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bundle = root / "bundle.json"
        self.digest = root / "bundle.sha256"
        self.data = {
            "pin": "aivexus.dart.running_total@0.1.0",
            "manifest": {
                "id": "aivexus.dart.running_total",
                "version": "0.1.0",
                "connector": {"provides": [
                    {"capability_id": "math.running_total",
                     "contract_id": "math.running_total.v1"}]},
                "payload": {"type": "archive"},
                "provenance": {"license": None},
                "validation": {"tests_passed": True, "test_report": "tests/report.json"},
                "security": {"reviewed": False},
            },
        }
        self.write()

    def write(self):
        raw = (json.dumps(self.data) + "\n").encode()
        self.bundle.write_bytes(raw)
        self.digest.write_text(hashlib.sha256(raw).hexdigest() + "\n")

    def test_reports_actual_missing_evidence_without_certifying(self):
        report = inspect(self.bundle, self.digest)
        self.assertFalse(report["ready_for_certification"])
        self.assertIn("ATTRIBUTABLE_LICENSE_EVIDENCE_MISSING", report["blockers"])
        self.assertIn("INDEPENDENT_SIGNED_SECURITY_REVIEW_MISSING", report["blockers"])
        self.assertIn("MATERIALIZED_SOURCE_BOUND_REVIEW_REQUIRED", report["blockers"])

    def test_tampered_bundle_rejected(self):
        self.bundle.write_bytes(self.bundle.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            inspect(self.bundle, self.digest)

    def test_wrong_contract_rejected(self):
        self.data["manifest"]["connector"]["provides"][0]["contract_id"] = "wrong.v1"
        self.write()
        with self.assertRaisesRegex(ValueError, "contract mismatch"):
            inspect(self.bundle, self.digest)


if __name__ == "__main__":
    unittest.main()
