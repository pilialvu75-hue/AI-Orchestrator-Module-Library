import json
import tempfile
import unittest
from pathlib import Path

from tools.resolve_coordinator_workers import resolve


class WorkerDispatchTests(unittest.TestCase):
    def test_only_enabled_owner_lane_worker_is_selected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / ".airlab/control-plane/automation-registry.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"automations": [
                {"enabled": True, "kind": "lane_worker", "owner_lane": "a",
                 "actor_id": "automation:a", "allowed_operations": ["claim"],
                 "write_capabilities": ["control_plane_mutation"],
                 "target_lane_policy": "owner_lane_only"},
                {"enabled": False, "kind": "lane_worker", "owner_lane": "b",
                 "actor_id": "automation:b", "allowed_operations": ["claim"],
                 "write_capabilities": ["control_plane_mutation"],
                 "target_lane_policy": "owner_lane_only"}
            ]}))
            result = resolve(root, {"requests": [
                {"request_id": "r1", "lane_id": "a"},
                {"request_id": "r2", "lane_id": "b"}
            ]})
            self.assertEqual(result["ready"][0]["authorized_actor_id"], "automation:a")
            self.assertEqual(result["deferred"][0]["reason"], "no_authorized_worker")
            self.assertFalse(result["submitted"])


if __name__ == "__main__":
    unittest.main()
