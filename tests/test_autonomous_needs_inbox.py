"""Real sandbox inbox transition for the tightly restricted needs-only profile.

The GitHub API is mocked only at the protected verifier boundary. We exercise
the actual claim, submitted packet, isolated transaction, canonical validator,
processed receipt, replay protection, and explicit G6 no-approval invariant.
"""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import control_plane_manager
import control_plane_inbox as inbox
import validate_control_plane

REPO = "pilialvu75-hue/AI-Orchestrator-Module-Library"
NOW = datetime(2026, 10, 18, 5, 0, tzinfo=timezone.utc)
LANE = "library-curation"


class AutonomousNeedsInboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / ".airlab", self.root / ".airlab")
        # PR CI checks out GitHub's synthetic merge with the current main.
        # That main may have a different live Researcher claim; isolate this
        # test's Library lane instead of depending on mutable repository state.
        lane_path = self.root / ".airlab/control-plane/workstreams/library-curation.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        lane["status"] = "READY"
        lane["active_claim"] = None
        lane.pop("review_packet", None)
        lane.pop("block_reason", None)
        lane.pop("current_gate_attestation", None)
        lane["evidence"] = []
        lane["reviewer"] = {
            "required": True, "state": "PENDING",
            "reviewed_by": None, "reviewed_at": None,
        }
        lane["gates"].update({
            "G0_CLAIM": "PENDING", "G1_IMPLEMENTATION": "PENDING",
            "G2_STATIC": "PENDING", "G3_CI": "PENDING",
            "G4_INTEGRATION": "PENDING",
            "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE",
            "G6_REVIEWER": "PENDING", "G7_CANONICAL_SYNC": "PENDING",
        })
        lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        self.claim_id = control_plane_manager.claim(
            LANE, "needs-only-queue-maintenance", REPO,
            "Update Library needs queue without modifying executable modules",
            branch="feat/needs-queue-test", root=self.root, now=NOW,
        )
        self.packet = {
            "schema_version": 1, "submitted_at": (NOW + timedelta(minutes=1)).isoformat(),
            "lane_id": LANE, "claim_id": self.claim_id,
            "work_item": "needs-only-queue-maintenance",
            "repository": REPO,
            "branch": "feat/needs-queue-test",
            "pull_request": 120,
            "summary": "Adjust a single catalog/needs.json queue entry",
            "changes": ["catalog/needs.json"],
            "evidence": [{"type": "ci", "ref": "https://github.com/owner/repo/actions/runs/99", "result": "PASS"}],
            "known_risks": [], "reviewer_checks": ["verify CI and exact metadata diff"],
            "roadmap_impact": {"material": False, "refs": []},
        }
        packet_file = self.root / "packet.json"
        packet_file.write_text(json.dumps(self.packet), encoding="utf-8")
        control_plane_manager.submit_review(
            LANE, packet_file, root=self.root,
            now=NOW + timedelta(minutes=1),
        )
        self.current = self.lane()
        self.identity = {
            "lane_id": LANE, "state_version": self.current["state_version"],
            "claim_id": self.claim_id,
            "packet_sha256": control_plane_manager._review_packet_digest(self.packet),
            "repository": REPO, "pr_number": 120, "head_sha": "a" * 40,
        }
        self.verified = {
            "identity": self.identity,
            "pr": {"number": 120},
            "scope": {
                "profile": "library-needs-only-v1",
                "canonical_identity": self.identity,
                "scope_verified": True, "runtime_applicable": False,
                "executable_changes": False,
                "changed_file": "catalog/needs.json",
                "file_blob_sha": "b" * 40,
            },
            "protected_run": {
                "repository": REPO, "run_id": 88, "run_attempt": 1,
                "head_sha": "c" * 40,
                "workflow_path": ".github/workflows/autonomous-ci-probe.yml",
            },
            "audit": {
                "canonical_identity": self.identity, "workflow_run_id": 99,
                "trusted_receipt": False, "completion_authorized": False,
                "gate_assessment": {
                    "G2_STATIC": "CI_PIPELINE_STEPS_VERIFIED",
                    "G3_CI": "EXACT_HEAD_SUCCESS_VERIFIED",
                },
            },
        }
        self.request = {
            "schema_version": 1, "request_id": "autonomous-needs-001",
            "actor_id": "chatgpt:library-curation", "lane_id": LANE,
            "operation": "autonomous_complete",
            "expected_state_version": self.current["state_version"],
            "payload": {
                "protected_run_id": 88, "run_attempt": 1,
                "protected_sha": "c" * 40,
            },
        }

    def lane(self):
        path = self.root / ".airlab/control-plane/workstreams/library-curation.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, request=None):
        request = self.request if request is None else request
        path = self.root / ".airlab/control-plane/inbox/pending" / (request["request_id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request), encoding="utf-8")
        return path

    def process(self, verified=None, request=None):
        path = self.write(request)
        with patch("control_plane_inbox._independently_verify_needs_completion",
                   return_value=self.verified if verified is None else verified):
            return inbox.process_one(
                path, root=self.root, now=NOW + timedelta(minutes=2),
            )

    def test_authenticated_needs_receipt_prepares_merge_but_does_not_release_claim(self):
        result = self.process()
        self.assertIn("applied", result)
        lane = self.lane()
        self.assertEqual(lane["status"], "REVIEW_REQUIRED")
        self.assertEqual(lane["active_claim"]["claim_id"], self.claim_id)
        self.assertEqual(lane["state_version"], self.current["state_version"] + 1)
        self.assertEqual(lane["gates"]["G6_REVIEWER"], "PENDING")
        self.assertEqual(lane["gates"]["G7_CANONICAL_SYNC"], "PENDING")
        self.assertEqual(lane["reviewer"]["state"], "PENDING")
        self.assertEqual(lane.get("autonomous_completion_history", []),
                         self.current.get("autonomous_completion_history", []))
        pending = lane["pending_needs_delivery"]
        self.assertEqual(pending["identity"], self.identity)
        self.assertEqual(pending["protected_run_id"], 88)
        self.assertEqual(pending["scope_blob_sha"], "b" * 40)
        self.assertEqual(validate_control_plane.validate(self.root), [])
        receipt_path = self.root / ".airlab/control-plane/inbox/processed/autonomous-needs-001.json"
        self.assertEqual(json.loads(receipt_path.read_text())["status"], "APPLIED")

    def test_real_finalization_requires_independently_confirmed_merged_catalog(self):
        self.assertIn("applied", self.process())
        lane = self.lane()
        delivery = {"pr_number": 120, "head_sha": "a" * 40,
                    "merge_commit_sha": "d" * 40, "file_blob_sha": "b" * 40}
        request = {
            **self.request,
            "request_id": "needs-delivered-claim-v-final",
            "operation": "autonomous_finalize_needs",
            "expected_state_version": lane["state_version"],
            "payload": delivery,
        }
        path = self.write(request)
        with patch("control_plane_inbox._independently_verify_needs_finalization",
                   return_value=delivery):
            result = inbox.process_one(path, root=self.root, now=NOW + timedelta(minutes=3))
        self.assertIn("applied", result)
        completed = self.lane()
        self.assertEqual(completed["status"], "READY")
        self.assertIsNone(completed["active_claim"])
        self.assertEqual(completed["state_version"], lane["state_version"] + 1)
        self.assertNotIn("pending_needs_delivery", completed)
        self.assertEqual(completed["gates"]["G7_CANONICAL_SYNC"], "PASS")
        self.assertEqual(completed["gates"]["G6_REVIEWER"], "PENDING")
        self.assertEqual(completed["reviewer"]["state"], "PENDING")
        self.assertEqual(completed["autonomous_completion_history"][-1]["decision"],
                         "MERGED_METADATA_ONLY")
        self.assertEqual(completed["autonomous_completion_history"][-1]["merge_commit_sha"],
                         "d" * 40)
        self.assertEqual(validate_control_plane.validate(self.root), [])

    def test_finalize_rejects_forged_merge_proof_without_releasing_claim(self):
        self.assertIn("applied", self.process())
        lane = self.lane()
        true_delivery = {"pr_number": 120, "head_sha": "a" * 40,
                         "merge_commit_sha": "d" * 40, "file_blob_sha": "b" * 40}
        for idx, bogus in enumerate((
            {**true_delivery, "file_blob_sha": "f" * 40},
            {**true_delivery, "pr_number": 121},
            {**true_delivery, "head_sha": "f" * 40},
            {**true_delivery, "merge_commit_sha": "invalid"},
        )):
            req = {**self.request, "operation": "autonomous_finalize_needs",
                   "request_id": f"needs-final-forgery-{idx}",
                   "expected_state_version": lane["state_version"],
                   "payload": bogus}
            path = self.write(req)
            with patch("control_plane_inbox._independently_verify_needs_finalization",
                       return_value=bogus):
                result = inbox.process_one(path, root=self.root, now=NOW + timedelta(minutes=3))
            self.assertIn("quarantined", result)
            self.assertEqual(self.lane(), lane)

    def test_replayed_completion_is_idempotent(self):
        self.assertIn("applied", self.process())
        lane = self.lane()
        replay = self.write()
        result = inbox.process_one(replay, root=self.root, now=NOW + timedelta(minutes=3))
        self.assertIn("duplicate-noop", result)
        self.assertEqual(lane, self.lane())

    def test_stale_version_blocks_network_and_keeps_lane(self):
        request = {**self.request, "expected_state_version": self.current["state_version"] - 1,
                   "request_id": "autonomous-needs-stale"}
        path = self.write(request)
        with patch("control_plane_inbox._independently_verify_needs_completion") as auth:
            result = inbox.process_one(path, root=self.root, now=NOW + timedelta(minutes=2))
        self.assertIn("quarantined", result)
        auth.assert_not_called()
        self.assertEqual(self.lane(), self.current)

    def test_unverified_and_broad_scope_rejected(self):
        bad = [
            {**self.verified, "identity": {**self.identity, "state_version": 0}},
            {**self.verified, "scope": {**self.verified["scope"], "changed_file": "tools/unsafe.py"}},
            {**self.verified, "scope": {**self.verified["scope"], "runtime_applicable": True}},
            {**self.verified, "audit": {**self.verified["audit"], "gate_assessment": {}}},
        ]
        for i, report in enumerate(bad):
            with self.subTest(i=i):
                request = {**self.request, "request_id": f"autonomous-needs-forged-{i}"}
                result = self.process(verified=report, request=request)
                self.assertIn("quarantined", result)
                self.assertEqual(self.lane(), self.current)

    def test_runtime_claim_or_material_roadmap_blocks(self):
        path = self.root / ".airlab/control-plane/workstreams/library-curation.json"
        lane = self.lane()
        lane["gates"]["G5_TARGET_RUNTIME"] = "PENDING"
        path.write_text(json.dumps(lane))
        self.assertIn("quarantined", self.process(request={**self.request, "request_id": "needs-runtime"}))
        lane = self.lane()
        lane["gates"]["G5_TARGET_RUNTIME"] = "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE"
        lane["review_packet"]["roadmap_impact"]["material"] = True
        path.write_text(json.dumps(lane))
        self.assertIn("quarantined", self.process(request={**self.request, "request_id": "needs-roadmap"}))

    def test_missing_protected_api_token_always_quarantines(self):
        path = self.write({**self.request, "request_id": "needs-no-token"})
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            result = inbox.process_one(
                path, root=self.root, now=NOW + timedelta(minutes=2))
        self.assertIn("quarantined", result)
        self.assertEqual(self.lane(), self.current)


if __name__ == "__main__":
    unittest.main()
