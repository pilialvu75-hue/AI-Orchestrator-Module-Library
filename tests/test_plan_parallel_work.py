import unittest

from tools.plan_parallel_work import plan


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

    def test_unknown_dependency_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            plan({"tasks": [{"id": "A", "lane": "a", "depends_on": ["X"]}]})


if __name__ == "__main__":
    unittest.main()
