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

    def test_conflicting_reimport_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = self.proposal()
            self.assertEqual(ingest(root, original)["created"], 1)
            changed = self.proposal()
            changed["proposals"][0]["novelty"] = ["topic:different"]
            with self.assertRaises(ValueError):
                ingest(root, changed)
            saved = json.loads(
                next((root / ".airlab/research-improvements/pending").glob("*.json")).read_text()
            )
            self.assertEqual(saved["proposal"]["novelty"], ["topic:quantization"])

    def test_conflicting_batch_does_not_import_earlier_new_items(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = self.proposal()
            ingest(root, original)
            batch = self.proposal()
            new_item = {**batch["proposals"][0], "proposal_id": "b" * 64}
            conflicting_item = {**batch["proposals"][0], "novelty": ["topic:changed"]}
            batch["proposals"] = [new_item, conflicting_item]
            with self.assertRaises(ValueError):
                ingest(root, batch)
            self.assertFalse(
                (root / ".airlab/research-improvements/pending" / ("b" * 64 + ".json")).exists()
            )

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
