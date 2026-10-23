import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from research_proposal_triage import report


class ProposalTriageTests(unittest.TestCase):
    def test_groups_exact_metadata_without_mutating_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pending = root / ".airlab/research-improvements/pending"
            pending.mkdir(parents=True)
            for identifier, capability, novelty in [
                ("a" * 64, "ai.local_inference", ["topic:quantization"]),
                ("b" * 64, "ai.local_inference", ["topic:quantization"]),
                ("c" * 64, "ai.acceleration_backend", ["topic:vulkan"]),
            ]:
                record = {
                    "state": "AWAITING_TRIAGE",
                    "proposal": {
                        "proposal_id": identifier, "capability_id": capability,
                        "status": "PROPOSED", "novelty": novelty,
                        "acceptance_gates": ["security_gates_pass"],
                    },
                }
                (pending / (identifier + ".json")).write_text(json.dumps(record))
            before = {p.name: p.read_bytes() for p in pending.iterdir()}
            result = report(root)
            self.assertEqual(result["total_pending"], 3)
            self.assertEqual([x["capability_id"] for x in result["review_queue"]], ["ai.local_inference", "ai.local_inference", "ai.acceleration_backend"])
            self.assertTrue(all(x["readiness"] == "UNVERIFIED" for x in result["review_queue"]))
            self.assertTrue(all(x["next_action"] == "validate_source_license_security_compatibility_and_tests" for x in result["review_queue"]))
            self.assertEqual(result["duplicate_review_count"], 1)
            self.assertEqual(result["exact_metadata_duplicate_groups"], [["a" * 64, "b" * 64]])
            self.assertEqual(result["by_capability"]["ai.local_inference"], 2)
            self.assertEqual(before, {p.name: p.read_bytes() for p in pending.iterdir()})

    def test_rejects_mismatched_filename(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pending = root / ".airlab/research-improvements/pending"
            pending.mkdir(parents=True)
            (pending / ("a" * 64 + ".json")).write_text(json.dumps({
                "state": "AWAITING_TRIAGE",
                "proposal": {"proposal_id": "b" * 64, "status": "PROPOSED"},
            }))
            with self.assertRaises(ValueError):
                report(root)


if __name__ == "__main__":
    unittest.main()
