import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_candidate_review_packet import packet


class CandidatePacketTests(unittest.TestCase):
    def test_handoff_shell_continuations(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/review-autonomous-public-dart.yml').read_text()
        step = workflow.split('Produce fixnum reviewer handoff', 1)[1].split('Publish source-bound', 1)[0]
        self.assertNotIn(chr(92) * 2 + chr(10), step)
        self.assertEqual(step.count(chr(92) + chr(10)), 4)

    def test_source_bound_blocked_packet(self):
        asset = "utility.int64_arithmetic.external.dartlang.fixnum"
        requests = {"schema": "aivexus.library.autonomous-public-dart-review-collection.v1",
                    "requests": [{"asset_id": asset, "security_reviewed": False,
                                  "certification_authorized": False,
                                  "source": {"repository": "https://github.com/dart-lang/core",
                                             "commit": "a" * 40, "payload_tree_sha256": "b" * 64,
                                             "license_sha256": "c" * 64},
                                  "tested_evidence": {"ci_run_id": 123, "ci_head_sha": "d" * 40}}]}
        preflight = {"schema": "aivexus.library.independent-review-preflight.v1",
                     "items": [{"asset_id": asset, "decision": "BLOCKED",
                                "certification_authorized": False,
                                "reasons": ["REVIEW_REQUIRED"]}]}
        result = packet(requests, preflight, asset)
        self.assertEqual(result["source_sha256"], "b" * 64)
        self.assertFalse(result["certification_authorized"])
        with self.assertRaises(ValueError):
            packet(requests, dict(preflight, items=[dict(preflight["items"][0], decision="APPROVED")]), asset)


if __name__ == "__main__":
    unittest.main()
