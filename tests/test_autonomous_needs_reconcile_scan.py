"""Regression tests for scheduled catch-up of protected Library needs receipts."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.autonomous_independent_gates import LIBRARY_REPOSITORY as REPO
from tools.autonomous_needs_reconcile_scan import reconcile_verified_needs

NOW = datetime(2026, 10, 18, 10, 15, tzinfo=timezone.utc)
RUN = {
    "id": 39118397690,
    "run_attempt": 1,
    "created_at": "2026-10-18T10:13:28Z",
    "event": "workflow_dispatch",
    "path": ".github/workflows/autonomous-ci-probe.yml",
    "head_branch": "main",
    "head_sha": "a" * 40,
    "status": "completed", "conclusion": "success",
    "repository": {"full_name": REPO},
}
LANE = {
    "id": "library-curation",
    "role": "worker",
    "status": "REVIEW_REQUIRED",
    "active_claim": {
        "claim_id": "claim",
        "repository": REPO,
        "started_at": "2026-10-18T10:08:39Z",
        "lease_until": "2026-10-18T22:08:39Z",
    },
    "review_packet": {"pull_request": 131},
}


class NeedsCatchUpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        path = self.root / ".airlab/control-plane/workstreams/library-curation.json"
        path.parent.mkdir(parents=True)
        self.path = path
        self.save(LANE)

    def save(self, content):
        self.path.write_text(json.dumps(content), encoding="utf-8")

    def call(self, runs=None, total=None, enqueue_result="pending/test.json"):
        runs = [RUN] if runs is None else runs
        total = len(runs) if total is None else total
        with patch("tools.autonomous_needs_reconcile_scan._validate_review_packet"), patch(
            "tools.autonomous_needs_reconcile_scan.fetch_json",
            return_value={"total_count": total, "workflow_runs": runs},
        ) as fetch, patch(
            "tools.autonomous_needs_reconcile_scan.enqueue_protected_needs_run",
            return_value=enqueue_result,
        ) as enqueue:
            result = reconcile_verified_needs(root=self.root, token="fake-token", now=NOW)
        return result, fetch, enqueue

    def test_valid_run_queues_only_after_separate_authenticated_enqueuer(self):
        result, fetch, enqueue = self.call()
        self.assertEqual(result, "pending/test.json")
        fetch.assert_called_once()
        self.assertIn("workflows/autonomous-ci-probe.yml/runs?", fetch.call_args.args[0])
        enqueue.assert_called_once_with(
            39118397690, token="fake-token", root=self.root, now=NOW,
        )

    def test_ineligible_lane_does_not_access_github(self):
        for changed in (
            {**LANE, "status": "READY"},
            {**LANE, "active_claim": None},
            {**LANE, "review_packet": None},
            {**LANE, "active_claim": {**LANE["active_claim"], "repository": "other/repo"}},
            {**LANE, "id": "library-researcher"},
        ):
            with self.subTest(lane=changed):
                self.save(changed)
                with patch("tools.autonomous_needs_reconcile_scan.fetch_json") as fetch:
                    self.assertIsNone(reconcile_verified_needs(
                        root=self.root, token="fake-token", now=NOW,
                    ))
                    fetch.assert_not_called()

    def test_failed_stale_or_unrelated_workflows_never_enqueue(self):
        bad = [
            {**RUN, "created_at": "2026-10-18T10:00:00Z"},
            {**RUN, "status": "in_progress"},
            {**RUN, "conclusion": "failure"},
            {**RUN, "event": "push"},
            {**RUN, "head_branch": "untrusted"},
            {**RUN, "path": ".github/workflows/other.yml"},
            {**RUN, "repository": {"full_name": "other/repo"}},
            {**RUN, "head_sha": "invalid"},
            {**RUN, "run_attempt": True},
        ]
        for run in bad:
            with self.subTest(run=run):
                result, _, enqueue = self.call(runs=[run])
                self.assertIsNone(result)
                enqueue.assert_not_called()

    def test_listing_must_have_github_count(self):
        for total in (-1, True, 0, "1"):
            with self.subTest(total=total):
                with self.assertRaisesRegex(ValueError, "invalid or incomplete"):
                    self.call(total=total)

    def test_enqueuer_can_refuse_run_without_promoting_lane(self):
        before = self.path.read_bytes()
        result, _, enqueue = self.call(enqueue_result=None)
        self.assertIsNone(result)
        enqueue.assert_called_once()
        self.assertEqual(self.path.read_bytes(), before)

    def test_newer_bad_receipt_does_not_block_older_valid_run(self):
        newer = {**RUN, "id": 39118397691,
                 "created_at": "2026-10-18T10:14:00Z"}
        def enqueue(run_id, **kwargs):
            if run_id == 39118397691:
                raise ValueError("protected artifact identity mismatch")
            return "pending/old-verified.json"
        with patch("tools.autonomous_needs_reconcile_scan._validate_review_packet"), patch(
            "tools.autonomous_needs_reconcile_scan.fetch_json",
            return_value={"total_count": 2, "workflow_runs": [newer, RUN]},
        ), patch(
            "tools.autonomous_needs_reconcile_scan.enqueue_protected_needs_run",
            side_effect=enqueue,
        ) as verifier:
            self.assertEqual(
                reconcile_verified_needs(root=self.root, token="fake-token", now=NOW),
                "pending/old-verified.json",
            )
        self.assertEqual([x.args[0] for x in verifier.call_args_list],
                         [39118397691, 39118397690])

    def test_no_token_refuses_before_network(self):
        with patch("tools.autonomous_needs_reconcile_scan._validate_review_packet"), patch(
            "tools.autonomous_needs_reconcile_scan.fetch_json"
        ) as fetch:
            with self.assertRaisesRegex(ValueError, "token"):
                reconcile_verified_needs(root=self.root, token="", now=NOW)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
