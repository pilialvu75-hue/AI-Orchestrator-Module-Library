"""Protected-run provenance metadata checks."""
import unittest

from tools.autonomous_protected_run import validate_protected_run

SHA = "a" * 40
REPO = "owner/repo"
PATH = ".github/workflows/autonomous-ci-probe.yml"
RUN = {"id": 55, "run_attempt": 1, "repository": {"full_name": REPO},
       "path": PATH, "head_branch": "main", "event": "workflow_dispatch",
       "head_sha": SHA, "status": "completed", "conclusion": "success"}


def check(run):
    return validate_protected_run(run, repository=REPO, workflow_path=PATH,
                                  head_sha=SHA, run_id=55, run_attempt=1)


class ProtectedRunTests(unittest.TestCase):
    def test_matching_run_is_not_completion_authority(self):
        result = check(RUN)
        self.assertFalse(result["authenticated"])
        self.assertFalse(result["completion_authorized"])

    def test_rejects_wrong_identity_or_incomplete_run(self):
        cases = [
            ("id", 56), ("id", True), ("run_attempt", 2),
            ("run_attempt", True), ("path", ".github/workflows/untrusted.yml"),
            ("head_branch", "feature"), ("event", "pull_request"),
            ("head_sha", "b" * 40), ("status", "in_progress"),
            ("conclusion", "failure"), ("conclusion", "skipped"),
            ("repository", {"full_name": "other/repo"}),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                check({**RUN, key: value})

    def test_rejects_invalid_expected_protected_sha(self):
        with self.assertRaises(ValueError):
            validate_protected_run(RUN, repository=REPO, workflow_path=PATH,
                                   head_sha="invalid", run_id=55, run_attempt=1)

    def test_rejects_missing_fields(self):
        for key in RUN:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check({k: v for k, v in RUN.items() if k != key})


if __name__ == "__main__":
    unittest.main()
