"""Regression checks for reviewer dispatch workflow contract.

Run: python3 -m unittest discover -s tests -p 'test_reviewer_recovery_contract.py'
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/reviewer-recovery-dispatch.yml"


class ReviewerRecoveryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_no_automatic_merge_or_approval(self):
        self.assertNotIn("gh pr merge", self.workflow)
        self.assertNotIn("gh pr review --approve", self.workflow)
        self.assertNotIn('"state=APPROVED"', self.workflow)

    def test_exact_head_idempotency(self):
        self.assertIn('head=pr["head"]["sha"]', self.workflow)
        self.assertIn('reviewer-recovery:v1:{number}:{head}', self.workflow)
        self.assertIn('if any(marker in c.get("body","") for c in comments):', self.workflow)

    def test_fail_closed_checks(self):
        self.assertIn('if not runs or any(', self.workflow)
        self.assertIn('r["conclusion"]!="success"', self.workflow)

    def test_explicit_legacy_draft_only(self):
        self.assertIn('if pr["draft"] and number != 117:', self.workflow)

    def test_no_claim_mutation(self):
        self.assertNotIn("resolve_stale_block", self.workflow)
        self.assertNotIn("promote_claim", self.workflow)


if __name__ == "__main__":
    unittest.main()
