import json
import tempfile
import unittest
from pathlib import Path
from tools.validate_coordinator_queue import validate


class QueueEligibilityTests(unittest.TestCase):
    def test_existing_lane_commitment_requires_acknowledgement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = root / ".airlab/control-plane"
            (base / "workstreams").mkdir(parents=True)
            (base / "canonical-state.json").write_text(json.dumps({
                "workstreams": [".airlab/control-plane/workstreams/a.json"]}))
            (base / "workstreams/a.json").write_text(json.dumps({
                "id": "a", "role": "worker", "activation": "active",
                "status": "READY", "active_claim": None,
                "next_action": "finish existing task"}))
            task = {"id": "A", "lane": "a", "repository": "owner/repo",
                    "scope": "bounded task"}
            self.assertIn("unreconciled_lane_next_action",
                          validate(root, {"tasks": [task]})["findings"][0]["reasons"])
            task["acknowledges_next_action"] = True
            self.assertTrue(validate(root, {"tasks": [task]})["all_eligible"])


if __name__ == "__main__":
    unittest.main()
