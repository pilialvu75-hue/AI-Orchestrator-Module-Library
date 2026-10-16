import json
import tempfile
import unittest
from pathlib import Path
from tools.reconcile_coordinator_dispatch import reconcile


class DispatchReceiptTests(unittest.TestCase):
    def test_observed_claim_is_not_confused_with_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = root / ".airlab/control-plane"
            (base / "workstreams").mkdir(parents=True)
            (base / "canonical-state.json").write_text(json.dumps({
                "workstreams": [".airlab/control-plane/workstreams/a.json"]}))
            lane = base / "workstreams/a.json"
            proposal = {"requests": [{"request_id": "r1", "lane_id": "a",
                        "expected_state_version": 2, "payload": {"work_item": "A"}}]}
            state = {"id": "a", "status": "READY", "state_version": 2, "active_claim": None}
            lane.write_text(json.dumps(state))
            self.assertEqual(reconcile(root, proposal)["receipts"][0]["status"],
                             "AWAITING_ACTOR_SUBMISSION")
            state["active_claim"] = {"work_item": "B"}
            lane.write_text(json.dumps(state))
            self.assertEqual(reconcile(root, proposal)["receipts"][0]["status"],
                             "CONFLICT_OTHER_CLAIM")
            state["active_claim"] = {"work_item": "A"}
            lane.write_text(json.dumps(state))
            self.assertEqual(reconcile(root, proposal)["receipts"][0]["status"],
                             "CLAIM_OBSERVED")


if __name__ == "__main__":
    unittest.main()
