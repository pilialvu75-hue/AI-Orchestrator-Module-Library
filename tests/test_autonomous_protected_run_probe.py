"""Protected workflow metadata must come from GitHub API, not caller JSON."""
import unittest
from unittest.mock import patch

from tools.autonomous_protected_run_probe import fetch_protected_run

REPO = "owner/repo"
SHA = "a" * 40
PATH = ".github/workflows/autonomous-ci-probe.yml"
RUN = {"id": 55, "run_attempt": 1, "repository": {"full_name": REPO},
       "path": PATH, "head_branch": "main", "event": "workflow_dispatch",
       "head_sha": SHA, "status": "completed", "conclusion": "success"}


def call():
    return fetch_protected_run(REPO, 55, 1, PATH, SHA, "fake-token")


class ProtectedRunProbeTests(unittest.TestCase):
    def test_fetches_exact_run_without_granting_authority(self):
        with patch("tools.autonomous_protected_run_probe.fetch_json", return_value=RUN) as fetch:
            result = call()
        self.assertEqual(fetch.call_args.args[0], "https://api.github.com/repos/owner/repo/actions/runs/55")
        self.assertFalse(result["completion_authorized"])
        self.assertFalse(result["authenticated"])

    def test_rejects_untrusted_run(self):
        with patch("tools.autonomous_protected_run_probe.fetch_json", return_value={**RUN, "head_branch": "feature"}):
            with self.assertRaises(ValueError):
                call()

    def test_rejects_invalid_input_without_network(self):
        for repository, run_id, attempt, sha, token in (
            ("owner/repo?x=y", 55, 1, SHA, "token"),
            (REPO, True, 1, SHA, "token"),
            (REPO, 55, 0, SHA, "token"),
            (REPO, 55, 1, "invalid", "token"),
            (REPO, 55, 1, SHA, ""),
        ):
            with self.subTest(repository=repository, run_id=run_id):
                with patch("tools.autonomous_protected_run_probe.fetch_json") as fetch:
                    with self.assertRaises(ValueError):
                        fetch_protected_run(repository, run_id, attempt, PATH, sha, token)
                    fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
