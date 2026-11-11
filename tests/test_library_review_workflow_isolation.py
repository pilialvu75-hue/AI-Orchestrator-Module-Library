import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_review_workflow_isolation import check_review_workflow


class WorkflowIsolationTests(unittest.TestCase):
    def test_repository_workflow(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/review-autonomous-public-dart.yml"
        self.assertEqual(check_review_workflow(path.read_text()), [])

    def test_permission_overrides_rejected(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/review-autonomous-public-dart.yml"
        original = path.read_text()
        for replacement in ("permissions:\\n  contents: write",
                            "permissions:\\n  contents: read\\n  actions: write",
                            "permissions: write-all"):
            with self.subTest(replacement=replacement):
                modified = original.replace("permissions:\\n  contents: read", replacement, 1)
                self.assertTrue(check_review_workflow(modified))
        self.assertTrue(check_review_workflow(original + "\\n    permissions:\\n      issues: write\\n"))

    def test_privileged_changes_rejected(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/review-autonomous-public-dart.yml"
        original = path.read_text()
        for injected in ("secrets.REVIEWER_KEY", "pull_request_target:", "contents: write",
                         "id-token: write", "self-hosted"):
            with self.subTest(injected=injected):
                self.assertTrue(check_review_workflow(original + "\n" + injected))


if __name__ == "__main__":
    unittest.main()
