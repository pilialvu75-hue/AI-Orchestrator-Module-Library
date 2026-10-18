"""Offline regression tests for automated needs-only dispatch and enqueue."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.autonomous_independent_gates import LIBRARY_REPOSITORY as REPO
from tools.autonomous_needs_dispatch import dispatch_ready_needs
from tools.autonomous_needs_enqueue import enqueue_protected_needs_run

LANE = "library-curation"
SHA = "a" * 40
IDENTITY = {
    "lane_id": LANE, "state_version": 9,
    "claim_id": "claim", "packet_sha256": "b" * 64,
    "repository": REPO, "pr_number": 120, "head_sha": SHA,
}
LANE_SNAPSHOT = {
    "id": LANE, "role": "worker", "status": "REVIEW_REQUIRED",
    "state_version": 9,
    "active_claim": {"claim_id": "claim", "repository": REPO,
                     "work_item": "update-needs",
                     "lease_until": "2030-10-18T00:00:00+00:00"},
    "review_packet": {"pull_request": 120},
}
AUDIT = {
    "ci_evidence": {"independent_gate_audit": {"canonical_identity": IDENTITY}},
    "identity": IDENTITY,
    "trusted_receipt": False, "completion_authorized": False,
}
SCOPE = {"canonical_identity": IDENTITY, "scope_verified": True}


class _Response:
    status = 204
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False


class AutonomousNeedsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        path = self.root / ".airlab/control-plane/workstreams/library-curation.json"
        path.parent.mkdir(parents=True)
        self.path = path
        self.save()

    def save(self, lane=None):
        self.path.write_text(json.dumps(LANE_SNAPSHOT if lane is None else lane))

    def test_dispatch_requires_live_exact_scope_and_ci_before_workflow(self):
        with patch("tools.autonomous_needs_dispatch._assert_claim_live"), patch(
            "tools.autonomous_needs_dispatch._validate_review_packet"
        ), patch("tools.autonomous_needs_dispatch.fetch_json", return_value={}), patch(
            "tools.autonomous_needs_dispatch.derive_canonical_receipt_identity",
            return_value=IDENTITY,
        ), patch("tools.autonomous_needs_dispatch.verify_needs_only_scope",
                 return_value=SCOPE), patch(
            "tools.autonomous_needs_dispatch.probe_ci",
            return_value={"head_sha": SHA, "trusted_receipt": False,
                          "completion_authorized": False},
        ), patch("tools.autonomous_needs_dispatch.urllib.request.urlopen",
                 return_value=_Response()) as open_url:
            self.assertTrue(dispatch_ready_needs(
                root=self.root, token="test-token", changed_commit_only=False,
            ))
        self.assertEqual(open_url.call_count, 1)
        request = open_url.call_args.args[0]
        self.assertIn(b'"ref": "main"', request.data)
        self.assertIn(b'"lane_id": "library-curation"', request.data)

    def test_no_review_packet_or_ineligible_lane_does_not_dispatch(self):
        for altered in ({**LANE_SNAPSHOT, "status": "READY"},
                        {**LANE_SNAPSHOT, "review_packet": None},
                        {**LANE_SNAPSHOT, "active_claim": None}):
            with self.subTest(lane=altered):
                self.save(altered)
                with patch("tools.autonomous_needs_dispatch.urllib.request.urlopen") as open_url:
                    self.assertFalse(dispatch_ready_needs(
                        root=self.root, token="test-token", changed_commit_only=False,
                    ))
                    open_url.assert_not_called()

    def test_missing_token_never_dispatches(self):
        with patch("tools.autonomous_needs_dispatch.urllib.request.urlopen") as open_url:
            with self.assertRaisesRegex(ValueError, "token"):
                dispatch_ready_needs(
                    root=self.root, token="", changed_commit_only=False,
                )
            open_url.assert_not_called()

    def _enqueue(self, *, artifact=AUDIT, scope=SCOPE):
        run = {"run_attempt": 1, "head_sha": "c" * 40}
        with patch("tools.autonomous_needs_enqueue._assert_claim_live"), patch(
            "tools.autonomous_needs_enqueue._validate_review_packet"
        ), patch("tools.autonomous_needs_enqueue.fetch_json",
                 side_effect=[run, {}]), patch(
            "tools.autonomous_needs_enqueue.derive_canonical_receipt_identity",
            return_value=IDENTITY,
        ), patch("tools.autonomous_needs_enqueue.probe_receipt_evidence",
                 return_value=artifact) as probe, patch(
            "tools.autonomous_needs_enqueue.verify_needs_only_scope",
            return_value=scope,
        ):
            result = enqueue_protected_needs_run(
                88, root=self.root, token="test-token",
            )
        return result, probe

    def test_successful_protected_run_queues_only_locator_not_approval(self):
        path, verifier = self._enqueue()
        self.assertIsNotNone(path)
        verifier.assert_called_once()
        request = json.loads((self.root / path).read_text())
        self.assertEqual(request["operation"], "autonomous_complete")
        self.assertEqual(request["expected_state_version"], 9)
        self.assertEqual(request["payload"], {
            "protected_run_id": 88, "run_attempt": 1,
            "protected_sha": "c" * 40,
        })
        self.assertNotIn("trusted_receipt", request["payload"])
        self.assertNotIn("completion_authorized", request["payload"])

    def test_duplicate_protected_run_is_idempotent(self):
        first, _ = self._enqueue()
        second, _ = self._enqueue()
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_forged_scope_or_receipt_never_queues(self):
        cases = [
            (AUDIT, {"canonical_identity": IDENTITY, "scope_verified": False}),
            ({**AUDIT, "trusted_receipt": True}, SCOPE),
            ({**AUDIT, "identity": {**IDENTITY, "state_version": 10}}, SCOPE),
        ]
        for i, (artifact, scope) in enumerate(cases):
            with self.subTest(i=i):
                with self.assertRaises(ValueError):
                    self._enqueue(artifact=artifact, scope=scope)
                inbox = self.root / ".airlab/control-plane/inbox/pending"
                self.assertFalse(inbox.exists() and list(inbox.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
