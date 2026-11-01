"""Static findings are explicit blockers and must match immutable source."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_independent_review_preflight import assess
from test_library_review_evidence_crosscheck import packet


class StaticFindingsPreflightTests(unittest.TestCase):
    def test_findings_block(self):
        requests, evidence = packet()
        item = requests["requests"][0]
        scan = {"schema": "aivexus.library.static-source-audit.v1",
                "items": [{"asset_id": item["asset_id"],
                           "source_payload_sha256": item["source"]["payload_tree_sha256"],
                           "static_scan_completed": True,
                           "findings": [{"rule": "SENSITIVE_IMPORT"}]}]}
        result = assess(requests, evidence, scan)
        self.assertIn("STATIC_SOURCE_SECURITY_FINDINGS", result["items"][0]["reasons"])
        scan["items"][0]["source_payload_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            assess(requests, evidence, scan)


if __name__ == "__main__":
    unittest.main()
