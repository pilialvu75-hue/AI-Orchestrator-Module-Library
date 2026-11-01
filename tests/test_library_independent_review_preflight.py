"""Offline tests for review preflight."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_independent_review_preflight import assess
from test_library_review_evidence_crosscheck import packet


class PreflightTests(unittest.TestCase):
    def test_clean_advisories_do_not_approve(self):
        requests, evidence = packet()
        result = assess(requests, evidence)
        self.assertEqual(result["items"][0]["decision"], "BLOCKED")
        self.assertFalse(result["certification_authorized"])

    def test_known_advisories_block(self):
        requests, evidence = packet()
        evidence["reports"][0]["packages"][0]["vulnerability_ids"] = ["GHSA-example"]
        evidence["reports"][0]["vulnerabilities_found"] = 1
        result = assess(requests, evidence)
        self.assertIn("KNOWN_UPSTREAM_ADVISORIES", result["items"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
