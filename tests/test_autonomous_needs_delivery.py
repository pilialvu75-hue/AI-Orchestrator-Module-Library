"""Delivery recovery and exact-head merge gate for needs-only Library changes."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.autonomous_independent_gates import LIBRARY_REPOSITORY as REPO
from tools.autonomous_needs_delivery import (
    _pending, enqueue_verified_delivery, merge_prepared_needs,
    verify_merged_delivery,
)
from tools.control_plane_manager import _review_packet_digest

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
PR_NUMBER = 120
HEAD = "a" * 40
BLOB = "b" * 40
MERGE = "d" * 40
PACKET = {"pull_request": PR_NUMBER, "roadmap_impact": {"material": False}}
IDENTITY = {
    "lane_id": "library-curation",
    "claim_id": "test-claim",
    "state_version": 3,
    "packet_sha256": _review_packet_digest(PACKET),
    "repository": REPO,
    "pr_number": PR_NUMBER,
    "head_sha": HEAD,
}
PENDING = {
    "profile": "library-needs-only-v1",
    "identity": IDENTITY,
    "changed_file": "catalog/needs.json",
    "scope_blob_sha": BLOB,
    "protected_run_id": 88,
    "protected_run_attempt": 1,
    "protected_sha": "c" * 40,
    "ci_run_id": 99,
}
LANE = {
    "id": "library-curation", "role": "worker",
    "status": "REVIEW_REQUIRED", "state_version": 4,
    "active_claim": {
        "claim_id": "test-claim", "repository": REPO,
        "lease_until": "2026-10-18T22:00:00+00:00",
    },
    "review_packet": PACKET,
    "pending_needs_delivery": PENDING,
    "gates": {"G6_REVIEWER": "PENDING",
              "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE"},
    "reviewer": {"state": "PENDING"},
}
PR = {
    "number": PR_NUMBER, "state": "closed", "merged": True,
    "draft": False, "merge_commit_sha": MERGE,
    "base": {"ref": "main", "repo": {"full_name": REPO}},
    "head": {"sha": HEAD, "repo": {"full_name": REPO}},
}
COMPARE = {
    "base_commit": {"sha": MERGE},
    "status": "ahead", "behind_by": 0,
}
CONTENT = {"path": "catalog/needs.json", "sha": BLOB, "type": "file"}


class SignedResponse:
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, _n=-1):
        return b'{"merged":true,"sha":"' + MERGE.encode() + b'"}'


class NeedsDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lane_path = self.root / ".airlab/control-plane/workstreams/library-curation.json"
        self.lane_path.parent.mkdir(parents=True, exist_ok=True)
        self.save(LANE)

    def save(self, value):
        self.lane_path.write_text(json.dumps(value), encoding="utf-8")

    def verified(self, *, pr=None, comparison=None, content=None):
        data = [PR if pr is None else pr,
                COMPARE if comparison is None else comparison,
                CONTENT if content is None else content]
        with patch("tools.autonomous_needs_delivery.fetch_json",
                   side_effect=data) as fetch:
            report = verify_merged_delivery(PENDING, "fake-token")
        return report, fetch

    def test_merged_pr_main_ancestry_and_exact_catalog_blob_verified(self):
        report, fetch = self.verified()
        self.assertEqual(report, {
            "pr_number": PR_NUMBER, "head_sha": HEAD,
            "merge_commit_sha": MERGE, "file_blob_sha": BLOB,
        })
        self.assertEqual(fetch.call_count, 3)
        self.assertIn(f"compare/{MERGE}...main", fetch.call_args_list[1].args[0])
        self.assertIn("ref=main", fetch.call_args_list[2].args[0])

    def test_no_completion_for_open_unmerged_wrong_head_or_forked_base(self):
        cases = [
            {**PR, "merged": False},
            {**PR, "state": "open"},
            {**PR, "head": {"sha": "f" * 40}},
            {**PR, "base": {"ref": "other", "repo": {"full_name": REPO}}},
            {**PR, "base": {"ref": "main", "repo": {"full_name": "attacker/fork"}}},
            {**PR, "merge_commit_sha": None},
        ]
        for pr in cases:
            with self.subTest(pr=pr), self.assertRaisesRegex(ValueError, "does not confirm"):
                self.verified(pr=pr)

    def test_no_completion_for_wrong_ancestry_or_overwritten_blob(self):
        for comparison in (
            {**COMPARE, "status": "diverged"},
            {**COMPARE, "behind_by": 1},
            {**COMPARE, "base_commit": {"sha": "e" * 40}},
        ):
            with self.subTest(comparison=comparison), self.assertRaisesRegex(
                ValueError, "not an ancestor"
            ):
                self.verified(comparison=comparison)
        with self.assertRaisesRegex(ValueError, "not been delivered"):
            self.verified(content={**CONTENT, "sha": "f" * 40})

    def test_prepared_state_persists_and_blocks_cross_lane_release(self):
        found = _pending(self.root)
        self.assertIsNotNone(found)
        self.assertEqual(found[3]["identity"], IDENTITY)
        for value in (
            {**LANE, "status": "READY"},
            {**LANE, "pending_needs_delivery": None},
        ):
            self.save(value)
            self.assertIsNone(_pending(self.root))
        self.save({**LANE, "pending_needs_delivery": {
            **PENDING, "identity": {**IDENTITY, "state_version": 1},
        }})
        with self.assertRaisesRegex(ValueError, "does not match"):
            _pending(self.root)

    def test_enqueuer_only_persists_untrusted_locator_after_independent_merge_check(self):
        with patch("tools.autonomous_needs_delivery.verify_merged_delivery",
                   return_value={"pr_number": PR_NUMBER, "head_sha": HEAD,
                                 "merge_commit_sha": MERGE, "file_blob_sha": BLOB}) as check:
            path = enqueue_verified_delivery(token="fake-token", root=self.root, now=NOW)
            self.assertIsNotNone(path)
            item = json.loads((self.root / path).read_text())
            self.assertEqual(item["operation"], "autonomous_finalize_needs")
            self.assertEqual(item["expected_state_version"], 4)
            self.assertEqual(item["payload"]["merge_commit_sha"], MERGE)
            self.assertNotIn("completion_authorized", item)
            self.assertIsNone(enqueue_verified_delivery(
                token="fake-token", root=self.root, now=NOW,
            ))
            self.assertEqual(check.call_count, 2)
        self.assertEqual(json.loads(self.lane_path.read_text()), LANE)

    def test_exact_head_sha_is_sent_to_protected_github_merge(self):
        open_pr = {**PR, "state": "open", "merged": False}
        verified = {"identity": IDENTITY,
                    "trusted_receipt": False, "completion_authorized": False}
        scope = {"file_blob_sha": BLOB}
        with patch("tools.autonomous_needs_delivery.fetch_json",
                   return_value=open_pr), patch(
                       "tools.autonomous_needs_delivery.verify_needs_only_scope",
                       return_value=scope) as scope_check, patch(
                           "tools.autonomous_needs_delivery.probe_receipt_evidence",
                           return_value=verified) as evidence, patch(
                               "tools.autonomous_needs_delivery.urllib.request.urlopen",
                               return_value=SignedResponse()) as urlopen, patch(
                                   "tools.autonomous_needs_delivery.verify_merged_delivery",
                                   return_value={"merge_commit_sha": MERGE}) as check:
            self.assertTrue(merge_prepared_needs(
                token="fake-token", root=self.root, now=NOW,
            ))
        scope_check.assert_called_once()
        evidence.assert_called_once()
        check.assert_called_once()
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_method(), "PUT")
        self.assertIn(f"/pulls/{PR_NUMBER}/merge", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["sha"], HEAD)
        self.assertEqual(body["merge_method"], "merge")
        self.assertEqual(json.loads(self.lane_path.read_text()), LANE)

    def test_rejected_worker_head_never_triggers_merge(self):
        open_pr = {**PR, "state": "open", "merged": False,
                   "head": {"sha": "f" * 40}}
        with patch("tools.autonomous_needs_delivery.fetch_json",
                   return_value=open_pr), patch(
                       "tools.autonomous_needs_delivery.urllib.request.urlopen"
                   ) as urlopen:
            with self.assertRaisesRegex(ValueError, "changed before"):
                merge_prepared_needs(token="fake-token", root=self.root, now=NOW)
            urlopen.assert_not_called()

    def test_already_merged_retry_is_idempotent(self):
        with patch("tools.autonomous_needs_delivery.fetch_json", return_value=PR), patch(
            "tools.autonomous_needs_delivery.verify_merged_delivery",
            return_value={"merge_commit_sha": MERGE},
        ) as check, patch(
            "tools.autonomous_needs_delivery.urllib.request.urlopen"
        ) as urlopen:
            self.assertTrue(merge_prepared_needs(token="fake-token", root=self.root, now=NOW))
            check.assert_called_once()
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
