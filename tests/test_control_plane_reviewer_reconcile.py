import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "control_plane_reviewer_reconcile",
    ROOT / "tools" / "control_plane_reviewer_reconcile.py",
)
reviewer_reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer_reconcile)


class ReviewerStaleBlockResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / ".airlab", self.root / ".airlab")
        self.pending = self.root / ".airlab/control-plane/inbox/pending"
        self.pending.mkdir(parents=True, exist_ok=True)
        lane_path = self.root / ".airlab/control-plane/workstreams/main-reviewer.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        lane["status"] = "BLOCKED"
        lane["active_claim"] = None
        lane["block_reason"] = {
            "code": "CLAIM_LEASE_EXPIRED",
            "work_item": "CP-HARDEN-07",
            "claim_id": "expired-claim-123",
            "resource_locks": ["contract:control-plane-wait-lifecycle"],
            "lease_until": "2026-10-03T05:00:00Z",
            "detected_at": "2026-10-03T05:10:00Z",
            "review_required": True,
        }
        lane["state_version"] = 40
        lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        reviewer_reconcile.control_plane_manager.project(
            root=self.root,
            now=datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.temp.cleanup()

    def _request(self, request_id, *, actor="chatgpt:main-reviewer", work_item="CP-HARDEN-07", claim_id="expired-claim-123"):
        path = self.pending / f"{request_id}.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "request_id": request_id,
            "actor_id": actor,
            "lane_id": "main-reviewer",
            "operation": "resolve_stale_block",
            "expected_state_version": 40,
            "payload": {
                "work_item": work_item,
                "claim_id": claim_id,
                "summary": "Reviewer verified the continued bounded work and exact merged evidence.",
                "next_action": "Claim the next bounded canonical work item.",
                "evidence_refs": ["PR #97", "merge:dcd6154"],
            },
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_reviewer_can_resolve_matching_stale_block_to_ready(self):
        path = self._request("resolve-stale-good")
        result = reviewer_reconcile.process_one(
            path,
            root=self.root,
            now=datetime(2026, 10, 3, 16, 30, tzinfo=timezone.utc),
        )
        self.assertIn("applied", result)
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/main-reviewer.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane["status"], "READY")
        self.assertIsNone(lane["active_claim"])
        self.assertNotIn("block_reason", lane)
        self.assertEqual(lane["stale_block_history"][-1]["work_item"], "CP-HARDEN-07")
        self.assertEqual(lane["reconciliation_events"][-1]["type"], "STALE_BLOCK_RESOLVED_BY_REVIEWER")

    def test_non_reviewer_actor_is_quarantined(self):
        path = self._request("resolve-stale-actor", actor="automation:main-reviewer")
        with self.assertRaisesRegex(ValueError, "restricted to chatgpt:main-reviewer"):
            reviewer_reconcile.process_one(
                path,
                root=self.root,
                now=datetime(2026, 10, 3, 16, 30, tzinfo=timezone.utc),
            )

    def test_mismatched_stale_identity_is_quarantined_without_lane_mutation(self):
        path = self._request("resolve-stale-mismatch", claim_id="wrong-claim")
        result = reviewer_reconcile.process_one(
            path,
            root=self.root,
            now=datetime(2026, 10, 3, 16, 30, tzinfo=timezone.utc),
        )
        self.assertIn("quarantined", result)
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/main-reviewer.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane["status"], "BLOCKED")
        self.assertEqual(lane["block_reason"]["claim_id"], "expired-claim-123")


if __name__ == "__main__":
    unittest.main()
