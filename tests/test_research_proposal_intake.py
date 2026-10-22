import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from research_proposal_intake import ingest


class ResearchProposalIntakeTests(unittest.TestCase):
    def proposal(self):
        return {"schema_version": 1, "kind": "research_improvement_proposals",
                "proposals": [{"proposal_id": "a" * 64, "capability_id": "ai.local_inference",
                               "novelty": ["topic:quantization"],
                               "acceptance_gates": ["security_gates_pass"],
                               "status": "PROPOSED", "created_at": "2026-10-22T00:00:00Z"}]}

    def test_idempotent_intake(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(ingest(root, self.proposal())["created"], 1)
            self.assertEqual(ingest(root, self.proposal())["existing"], 1)
            saved = json.loads(next((root / ".airlab/research-improvements/pending").glob("*.json")).read_text())
            self.assertEqual(saved["state"], "AWAITING_TRIAGE")

    def test_invalid_batch_does_not_write_partial_data(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = self.proposal()
            payload["proposals"].append({**payload["proposals"][0], "proposal_id": "../bad"})
            with self.assertRaises(ValueError):
                ingest(root, payload)
            self.assertFalse((root / ".airlab/research-improvements").exists())


if __name__ == "__main__":
    unittest.main()
