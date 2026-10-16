import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_coordinator_claims import prepare


class CoordinatorClaimsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        base = self.root / ".airlab/control-plane"
        (base / "workstreams").mkdir(parents=True)
        (base / "canonical-state.json").write_text(json.dumps({
            "workstreams": [".airlab/control-plane/workstreams/worker.json"]
        }))
        self.lane_file = base / "workstreams/worker.json"
        self.lane_file.write_text(json.dumps({
            "id": "worker", "role": "worker", "activation": "active",
            "status": "READY", "state_version": 7, "active_claim": None,
        }))
        self.queue = {"revision": 4, "tasks": [{
            "id": "task-1", "lane": "worker", "repository": "owner/repo",
            "scope": "bounded feature",
        }]}
        self.plan = {"assignments": [{"task": "task-1", "lane": "worker"}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_proposals_are_not_submitted(self):
        result = prepare(self.root, self.plan, self.queue)
        self.assertFalse(result["submitted"])
        self.assertEqual(result["requests"][0]["expected_state_version"], 7)
        self.assertEqual(result["requests"][0]["operation"], "claim")
        self.assertEqual(result["requests"][0]["submission_status"], "AWAITING_AUTHORIZED_ACTOR")

    def test_claim_collision_fails_closed(self):
        lane = json.loads(self.lane_file.read_text())
        lane["active_claim"] = {"claim_id": "existing"}
        self.lane_file.write_text(json.dumps(lane))
        with self.assertRaisesRegex(ValueError, "unavailable"):
            prepare(self.root, self.plan, self.queue)

    def test_missing_scope_fails_closed(self):
        del self.queue["tasks"][0]["scope"]
        with self.assertRaisesRegex(ValueError, "scope"):
            prepare(self.root, self.plan, self.queue)


if __name__ == "__main__":
    unittest.main()
