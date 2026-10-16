"""Mocked API tests for the read-only GitHub CI probe."""
import unittest
from unittest.mock import patch

from tools.autonomous_ci_probe import probe

SHA = "a" * 40
REPO = "owner/repo"
PR = {"number": 120, "base": {"repo": {"full_name": REPO}}, "state": "open", "head": {"sha": SHA, "repo": {"full_name": REPO}}}
CHECK = {"name": "Validate Module Library", "head_sha": SHA,
         "status": "completed", "conclusion": "success",
         "app": {"slug": "github-actions"}, "id": 7, "details_url": "https://github.com/owner/repo/actions/runs/99/job/1"}


class ProbeTests(unittest.TestCase):
    def test_reads_exact_head_and_returns_non_authoritative_result(self):
        with patch("tools.autonomous_ci_probe.fetch_json",
                   side_effect=[PR, {"total_count": 1, "check_runs": [CHECK]}, {"total_count": 1, "workflow_runs": [{"id": 99, "head_sha": SHA, "status": "completed", "conclusion": "success", "repository": {"full_name": REPO}}]}]) as fetch:
            result = probe(REPO, 120, ["Validate Module Library"], "fake-token")
        self.assertEqual(fetch.call_count, 3)
        self.assertIn(f"/commits/{SHA}/check-runs?", fetch.call_args_list[1].args[0])
        self.assertFalse(result["completion_authorized"])

    def test_rejects_missing_token_before_network(self):
        with patch("tools.autonomous_ci_probe.fetch_json") as fetch:
            with self.assertRaises(ValueError):
                probe(REPO, 120, ["Validate Module Library"], "")
            fetch.assert_not_called()

    def test_rejects_incomplete_pagination(self):
        with patch("tools.autonomous_ci_probe.fetch_json",
                   side_effect=[PR, {"total_count": 101, "check_runs": [CHECK]}]):
            with self.assertRaises(ValueError):
                probe(REPO, 120, ["Validate Module Library"], "fake-token")

    def test_rejects_wrong_pr_identity(self):
        for bad_pr in (
            {**PR, "number": 121},
            {**PR, "base": {"repo": {"full_name": "other/repo"}}},
            {key: value for key, value in PR.items() if key != "number"},
        ):
            with self.subTest(pr=bad_pr):
                with patch("tools.autonomous_ci_probe.fetch_json", return_value=bad_pr):
                    with self.assertRaises(ValueError):
                        probe(REPO, 120, ["Validate Module Library"], "fake-token")

    def test_rejects_changed_head(self):
        with patch("tools.autonomous_ci_probe.fetch_json",
                   side_effect=[PR, {"total_count": 1, "check_runs": [{**CHECK, "head_sha": "b" * 40}]}, {"total_count": 1, "workflow_runs": [{"id": 99, "head_sha": SHA, "status": "completed", "conclusion": "success", "repository": {"full_name": REPO}}]}]):
            with self.assertRaises(ValueError):
                probe(REPO, 120, ["Validate Module Library"], "fake-token")


if __name__ == "__main__":
    unittest.main()
