"""Protect the independent review and publication permission boundary."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WorkflowPermissionsTest(unittest.TestCase):
    def test_review_producer_read_only(self):
        workflow = (ROOT / ".github/workflows/review-autonomous-public-dart.yml").read_text()
        self.assertIn("permissions:\n  contents: read\n", workflow)
        self.assertNotIn("contents: write", workflow)

    def test_publisher_uses_public_verification_key(self):
        workflow = (ROOT / ".github/workflows/certify-intake.yml").read_text()
        self.assertIn("LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM", workflow)

if __name__ == "__main__":
    unittest.main()
