"""Regression checks for the unsigned review handoff and publisher boundary."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorkflowPermissionsTest(unittest.TestCase):
    def test_review_producer_read_only(self):
        workflow = (ROOT / ".github/workflows/review-autonomous-public-dart.yml").read_text()
        self.assertIn("permissions:\n  contents: read\n", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn('assert report["certification_authorized"] is False', workflow)
        self.assertIn('assert item["reviewer_signature_present"] is False', workflow)

    def test_publisher_uses_public_verification_key(self):
        workflow = (ROOT / ".github/workflows/certify-intake.yml").read_text()
        self.assertIn("LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM", workflow)
        self.assertIn("python tools/library_autopilot.py", workflow)

    def test_review_preflight_remains_blocking(self):
        source = (ROOT / "tools/library_independent_review_preflight.py").read_text()
        self.assertIn('"decision": "BLOCKED"', source)
        self.assertIn('"certification_authorized": False', source)
        self.assertIn('"PROTECTED_REVIEWER_SIGNATURE_REQUIRED"', source)


if __name__ == "__main__":
    unittest.main()
