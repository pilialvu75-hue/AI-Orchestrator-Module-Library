"""Regression checks for the trusted accept/promote -> unprivileged consumer handoff."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SignedReviewWorkflowTests(unittest.TestCase):
    def test_no_missing_automatic_certification_handoff(self):
        text = (ROOT / ".github/workflows/accept-signed-fixnum-review.yml").read_text()
        self.assertIn("python3 tools/library_signed_review_stage.py", text)
        self.assertIn("--apply", text)
        self.assertIn("python3 tools/library_pipeline.py promote", text)
        self.assertIn("python3 tools/library_autopilot.py", text)
        self.assertIn("git add -A -- catalog modules intake packages", text)
        self.assertIn("git push origin HEAD:main", text)
        self.assertIn("LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM:", text)
        self.assertNotIn("run: dart ", text)
        self.assertNotIn("secrets.", text)

    def test_consumer_is_separate_unprivileged_workflow_run(self):
        consumer = (ROOT / ".github/workflows/prove-certified-consumer.yml").read_text()
        self.assertIn("workflow_run:", consumer)
        self.assertIn("Accept independent signed fixnum review and stage certification", consumer)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", consumer)
        self.assertIn("permissions: {}", consumer)
        self.assertIn("persist-credentials: false", consumer)
        self.assertIn("tools/library_consumer_execution.py", consumer)


if __name__ == "__main__":
    unittest.main()
