import unittest
from tools.gate_coordinator_assignments import gate


class CoordinatorEligibilityGateTests(unittest.TestCase):
    def test_ineligible_assignment_fails_closed(self):
        plan = {"assignments": [{"task": "A", "lane": "cantiere"}]}
        audit = {"findings": [{"task": "A", "lane": "cantiere",
                 "eligible": False, "reasons": ["unreconciled_lane_next_action"]}]}
        with self.assertRaisesRegex(ValueError, "ineligible"):
            gate(plan, audit)
        audit["findings"][0]["eligible"] = True
        self.assertEqual(gate(plan, audit)["gate"], "PASS")

    def test_missing_or_mismatched_audit_fails_closed(self):
        plan = {"assignments": [{"task": "A", "lane": "cantiere"}]}
        with self.assertRaises(ValueError):
            gate(plan, {"findings": []})
        with self.assertRaises(ValueError):
            gate(plan, {"findings": [{"task": "A", "lane": "other", "eligible": True}]})


if __name__ == "__main__":
    unittest.main()
