import unittest
import json
import tempfile
from pathlib import Path

from tools.plan_parallel_work import plan, plan_from_canonical


class ParallelWorkPlannerTests(unittest.TestCase):
    def test_independent_tasks_run_in_parallel(self):
        result = plan({"tasks": [
            {"id": "A", "lane": "a"}, {"id": "B", "lane": "b"},
            {"id": "C", "lane": "c"}],
            "lanes": [{"id": x} for x in ("a", "b", "c")], "max_parallel": 3})
        self.assertEqual([x["task"] for x in result["assignments"]], ["A", "B", "C"])
        self.assertFalse(result["state_mutated"])

    def test_pending_dependency_does_not_block_other_lane(self):
        result = plan({"tasks": [
            {"id": "X", "lane": "a", "status": "IMPLEMENTING"},
            {"id": "A", "lane": "a", "depends_on": ["X"]},
            {"id": "B", "lane": "b"}],
            "lanes": [{"id": "a", "busy": True}, {"id": "b"}]})
        self.assertEqual([x["task"] for x in result["assignments"]], ["B"])

    def test_owner_decision_stays_pending(self):
        result = plan({"tasks": [
            {"id": "proposal", "lane": "a", "proposal_requires_owner": True},
            {"id": "normal", "lane": "b"}],
            "lanes": [{"id": "a"}, {"id": "b"}]})
        self.assertEqual(result["assignments"][0]["task"], "normal")
        self.assertEqual(result["deferred"][0]["reason"], "owner_decision_required")

    def test_duplicate_task_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate task"):
            plan({"tasks": [{"id": "A", "lane": "a"}, {"id": "A", "lane": "b"}]})

    def test_completed_task_is_never_reassigned(self):
        with self.assertRaisesRegex(ValueError, "completed task"):
            plan({"tasks": [{"id": "A", "lane": "a"}],
                  "lanes": [{"id": "a"}], "completed": ["A"]})

    def test_unknown_lane_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown lane"):
            plan({"tasks": [{"id": "A", "lane": "missing"}],
                  "lanes": [{"id": "a"}]})

    def test_unknown_dependency_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            plan({"tasks": [{"id": "A", "lane": "a", "depends_on": ["X"]}]})


    def test_canonical_claim_blocks_only_its_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / ".airlab/control-plane"
            (base / "workstreams").mkdir(parents=True)
            (base / "canonical-state.json").write_text(json.dumps({
                "workstreams": [
                    ".airlab/control-plane/workstreams/a.json",
                    ".airlab/control-plane/workstreams/b.json",
                    ".airlab/control-plane/workstreams/reviewer.json",
                ]
            }))
            for name, role, claim in [
                ("a", "worker", {"claim_id": "busy"}),
                ("b", "worker", None),
                ("reviewer", "reviewer", None),
            ]:
                (base / "workstreams" / (name + ".json")).write_text(json.dumps({
                    "id": name, "role": role, "activation": "active",
                    "status": "READY", "active_claim": claim,
                }))
            result = plan_from_canonical(root, [
                {"id": "A", "lane": "a"}, {"id": "B", "lane": "b"},
                {"id": "R", "lane": "reviewer"},
            ])
            self.assertEqual([a["task"] for a in result["assignments"]], ["B"])
            self.assertEqual([d["reason"] for d in result["deferred"]],
                             ["lane_unavailable", "lane_unavailable"])

    def test_canonical_nonready_lane_is_not_scheduled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / ".airlab/control-plane"
            (base / "workstreams").mkdir(parents=True)
            (base / "canonical-state.json").write_text(json.dumps({
                "workstreams": [".airlab/control-plane/workstreams/a.json"]
            }))
            (base / "workstreams/a.json").write_text(json.dumps({
                "id": "a", "role": "worker", "activation": "active",
                "status": "REVIEW_REQUIRED", "active_claim": None,
            }))
            result = plan_from_canonical(root, [{"id": "A", "lane": "a"}])
            self.assertEqual(result["assignments"], [])


if __name__ == "__main__":
    unittest.main()
