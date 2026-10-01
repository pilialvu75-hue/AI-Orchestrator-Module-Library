import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "control_plane_manager",
    ROOT / "tools" / "control_plane_manager.py",
)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class ControlPlaneManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".airlab/control-plane/workstreams").mkdir(parents=True)
        canonical = json.loads((ROOT / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
        self.paths = canonical["workstreams"][:2]
        canonical["workstreams"] = self.paths
        canonical["claim_policy"] = {
            "default_lease_hours": 12,
            "max_lease_hours": 24,
            "stale_action": "BLOCKED_REQUIRES_REVIEWER",
        }
        (self.root / ".airlab/control-plane/canonical-state.json").write_text(
            json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
        )
        for rel in self.paths:
            src = ROOT / rel
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            lane = json.loads(dst.read_text(encoding="utf-8"))
            lane["status"] = "READY"
            lane["active_claim"] = None
            lane.pop("review_packet", None)
            lane.pop("block_reason", None)
            lane.setdefault("gates", {})["G0_CLAIM"] = "PENDING"
            if lane.get("role") != "reviewer":
                lane.setdefault("reviewer", {})["state"] = "PENDING"
            dst.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_claim_prevents_duplicate_work_item(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        manager.claim(
            "cantiere",
            "issue-123",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        with self.assertRaisesRegex(ValueError, "already claimed"):
            manager.claim(
                "main-reviewer",
                "issue-123",
                "owner/repo",
                "duplicate",
                root=self.root,
                now=now,
            )

    def test_claim_resets_previous_review_state(self):
        path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(path.read_text(encoding="utf-8"))
        previous_history_count = len(lane.get("review_packet_history", []))
        lane["reviewer"] = {
            "required": True,
            "state": "APPROVED",
            "reviewed_by": "main-reviewer",
            "reviewed_at": "2026-10-01T07:00:00Z",
        }
        lane["evidence"] = [{"type": "ci", "ref": "old", "result": "PASS"}]
        lane["review_packet"] = {
            "schema_version": 1,
            "claim_id": "old-claim",
            "work_item": "old-work",
        }
        for gate in ("G0_CLAIM", "G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION", "G6_REVIEWER", "G7_CANONICAL_SYNC"):
            lane["gates"][gate] = "PASS"
        path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

        manager.claim(
            "cantiere",
            "fresh-work",
            "owner/repo",
            "new bounded work",
            root=self.root,
            now=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
        )
        lane = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(lane["reviewer"]["state"], "PENDING")
        self.assertIsNone(lane["reviewer"]["reviewed_by"])
        self.assertEqual(lane["evidence"], [])
        self.assertNotIn("review_packet", lane)
        self.assertEqual(len(lane["review_packet_history"]), previous_history_count + 1)
        self.assertEqual(lane["review_packet_history"][-1]["claim_id"], "old-claim")
        self.assertEqual(lane["gates"]["G0_CLAIM"], "PASS")
        for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION", "G6_REVIEWER", "G7_CANONICAL_SYNC"):
            self.assertEqual(lane["gates"][gate], "PENDING")
        self.assertEqual(lane["gates"]["G5_TARGET_RUNTIME"], "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE")

    def test_heartbeat_extends_lease(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        manager.claim(
            "cantiere",
            "issue-124",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        extended = manager.heartbeat(
            "cantiere",
            lease_hours=6,
            root=self.root,
            now=now + timedelta(hours=2),
        )
        self.assertEqual(extended, "2026-10-01T16:00:00Z")

    def test_expired_heartbeat_cannot_resurrect_claim(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        manager.claim(
            "cantiere",
            "expired-heartbeat",
            "owner/repo",
            "bounded fix",
            lease_hours=1,
            root=self.root,
            now=now,
        )
        with self.assertRaisesRegex(ValueError, "claim lease expired"):
            manager.heartbeat(
                "cantiere",
                root=self.root,
                now=now + timedelta(hours=2),
            )

    def test_expired_claim_blocks_for_reviewer(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        manager.claim(
            "cantiere",
            "issue-125",
            "owner/repo",
            "bounded fix",
            lease_hours=1,
            root=self.root,
            now=now,
        )
        manager.reconcile(root=self.root, now=now + timedelta(hours=2))
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/cantiere.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane["status"], "BLOCKED")
        self.assertIsNone(lane["active_claim"])
        self.assertEqual(lane["block_reason"]["code"], "CLAIM_LEASE_EXPIRED")
        self.assertTrue(lane["block_reason"]["review_required"])

    def test_submit_review_requires_matching_claim(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        claim_id = manager.claim(
            "cantiere",
            "issue-126",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        packet = {
            "schema_version": 1,
            "submitted_at": "2026-10-01T09:00:00Z",
            "lane_id": "cantiere",
            "claim_id": claim_id,
            "work_item": "issue-126",
            "repository": "owner/repo",
            "branch": "fix/issue-126",
            "pull_request": 126,
            "summary": "Implemented bounded fix.",
            "changes": ["Changed one bounded behavior."],
            "evidence": [{"type": "test", "ref": "unit-test", "result": "PASS", "note": None}],
            "known_risks": [],
            "reviewer_checks": ["Verify no scope drift."],
            "roadmap_impact": {"material": False, "refs": []},
        }
        packet_path = self.root / "packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        manager.submit_review("cantiere", packet_path, root=self.root, now=now + timedelta(hours=1))
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/cantiere.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane["status"], "REVIEW_REQUIRED")
        self.assertEqual(lane["review_packet"]["claim_id"], claim_id)
        self.assertEqual(lane["evidence"][0]["result"], "PASS")
        self.assertIsNotNone(lane["active_claim"])
        self.assertEqual(lane["last_checkpoint"]["kind"], "REVIEW_HANDOFF")
        self.assertEqual(lane["last_checkpoint"]["claim_id"], claim_id)

    def test_submit_review_rejects_wrong_claim(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        manager.claim(
            "cantiere",
            "issue-127",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        packet = {
            "schema_version": 1,
            "submitted_at": "2026-10-01T09:00:00Z",
            "lane_id": "cantiere",
            "claim_id": "wrong-claim",
            "work_item": "issue-127",
            "repository": "owner/repo",
            "summary": "Implemented bounded fix.",
            "changes": ["Changed one bounded behavior."],
            "evidence": [{"type": "test", "ref": "unit-test", "result": "PASS"}],
            "known_risks": [],
            "reviewer_checks": ["Verify claim."],
            "roadmap_impact": {"material": False, "refs": []},
        }
        packet_path = self.root / "bad-packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "claim_id mismatch"):
            manager.submit_review("cantiere", packet_path, root=self.root, now=now + timedelta(hours=1))

    def test_submit_review_rejects_schema_invalid_changes(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        claim_id = manager.claim(
            "cantiere",
            "schema-invalid",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        packet = {
            "schema_version": 1,
            "submitted_at": "2026-10-01T09:00:00Z",
            "lane_id": "cantiere",
            "claim_id": claim_id,
            "work_item": "schema-invalid",
            "repository": "owner/repo",
            "summary": "Implemented bounded fix.",
            "changes": [{"description": "not allowed by schema"}],
            "evidence": [{"type": "test", "ref": "unit-test", "result": "PASS"}],
            "known_risks": [],
            "reviewer_checks": ["Verify claim."],
            "roadmap_impact": {"material": False, "refs": []},
        }
        packet_path = self.root / "schema-invalid.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changes must be"):
            manager.submit_review("cantiere", packet_path, root=self.root, now=now + timedelta(hours=1))

    def _submit_ready_review(self, work_item="issue-review"):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        claim_id = manager.claim(
            "cantiere",
            work_item,
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
            lane["gates"][gate] = "PASS"
        lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        packet = {
            "schema_version": 1,
            "submitted_at": "2026-10-01T09:00:00Z",
            "lane_id": "cantiere",
            "claim_id": claim_id,
            "work_item": work_item,
            "repository": "owner/repo",
            "summary": "Implemented bounded fix.",
            "changes": ["Changed one bounded behavior."],
            "evidence": [{"type": "test", "ref": "unit-test", "result": "PASS"}],
            "known_risks": [],
            "reviewer_checks": ["Verify no scope drift."],
            "roadmap_impact": {"material": False, "refs": []},
        }
        packet_path = self.root / f"{work_item}.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        manager.submit_review("cantiere", packet_path, root=self.root, now=now + timedelta(hours=1))
        return claim_id, now

    def test_review_inbox_reads_raw_lane_even_if_projection_is_stale(self):
        claim_id, now = self._submit_ready_review("issue-inbox")
        canonical_path = self.root / ".airlab/control-plane/canonical-state.json"
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        canonical["projection"]["review_required"] = []
        for lane in canonical["projection"]["lanes"]:
            if lane["id"] == "cantiere":
                lane["status"] = "IMPLEMENTING"
                lane["state_version"] = 0
        canonical_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")

        inbox = manager.review_inbox(root=self.root)
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["lane_id"], "cantiere")
        self.assertEqual(inbox[0]["claim_id"], claim_id)
        self.assertTrue(inbox[0]["packet_valid"])

    def test_review_accept_rejects_pending_required_gate(self):
        claim_id, now = self._submit_ready_review("issue-gate")
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        lane["gates"]["G3_CI"] = "PENDING"
        lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "G3_CI"):
            manager.review_accept(
                "cantiere",
                summary="Should not pass.",
                next_action="none",
                root=self.root,
                now=now + timedelta(hours=2),
            )

    def test_review_accept_releases_claim_and_returns_ready(self):
        claim_id, now = self._submit_ready_review("issue-accept")
        manager.review_accept(
            "cantiere",
            summary="Reviewed and accepted.",
            next_action="Run physical acceptance.",
            evidence_refs=["PR #1", "CI #2"],
            root=self.root,
            now=now + timedelta(hours=2),
        )
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/cantiere.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane["status"], "READY")
        self.assertIsNone(lane["active_claim"])
        self.assertEqual(lane["reviewer"]["state"], "APPROVED")
        self.assertEqual(lane["gates"]["G6_REVIEWER"], "PASS")
        self.assertEqual(lane["gates"]["G7_CANONICAL_SYNC"], "PASS")
        self.assertEqual(lane["last_checkpoint"]["kind"], "REVIEW_ACCEPTED")
        self.assertEqual(lane["last_checkpoint"]["claim_id"], claim_id)
        self.assertEqual(lane["next_action"], "Run physical acceptance.")

    def test_material_roadmap_impact_keeps_sync_gate_pending(self):
        claim_id, now = self._submit_ready_review("issue-roadmap")
        path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(path.read_text(encoding="utf-8"))
        lane["review_packet"]["roadmap_impact"] = {
            "material": True,
            "refs": [".airlab/roadmap.yaml#L1"],
        }
        path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        manager.review_accept(
            "cantiere",
            summary="Implementation accepted; roadmap still needs sync.",
            next_action="Sync roadmap.",
            root=self.root,
            now=now + timedelta(hours=2),
        )
        lane = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(lane["gates"]["G7_CANONICAL_SYNC"], "PENDING_ROADMAP_SYNC")

    def test_material_roadmap_impact_can_assert_verified_sync(self):
        claim_id, now = self._submit_ready_review("issue-roadmap-synced")
        path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(path.read_text(encoding="utf-8"))
        lane["review_packet"]["roadmap_impact"] = {
            "material": True,
            "refs": [".airlab/roadmap.yaml#L1"],
        }
        path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        manager.review_accept(
            "cantiere",
            summary="Implementation and roadmap sync accepted.",
            next_action="Continue.",
            roadmap_synced=True,
            root=self.root,
            now=now + timedelta(hours=2),
        )
        lane = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(lane["gates"]["G7_CANONICAL_SYNC"], "PASS")

    def test_review_rework_keeps_claim_and_returns_implementing(self):
        claim_id, now = self._submit_ready_review("issue-rework")
        manager.review_rework(
            "cantiere",
            reason="Regression coverage incomplete.",
            next_action="Add the missing regression test.",
            root=self.root,
            now=now + timedelta(hours=2),
        )
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/cantiere.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane["status"], "IMPLEMENTING")
        self.assertEqual(lane["active_claim"]["claim_id"], claim_id)
        self.assertEqual(lane["reviewer"]["state"], "CHANGES_REQUESTED")
        self.assertEqual(lane["last_checkpoint"]["kind"], "REVIEW_REWORK")
        self.assertEqual(lane["next_action"], "Add the missing regression test.")

    def test_checkpoint_watch_surfaces_claim_without_recent_checkpoint(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        manager.claim(
            "cantiere",
            "issue-128",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        self.assertTrue(manager.project(root=self.root, now=now + timedelta(hours=2, minutes=1)))
        canonical = json.loads(
            (self.root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8")
        )
        watch = canonical["projection"]["checkpoint_watch"]
        self.assertEqual(len(watch), 1)
        self.assertEqual(watch[0]["lane"], "cantiere")
        self.assertEqual(watch[0]["reason"], "NO_CHECKPOINT_YET")
        self.assertEqual(watch[0]["due_since"], "2026-10-01T10:00:00Z")

    def test_recent_checkpoint_clears_checkpoint_watch(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        claim_id = manager.claim(
            "cantiere",
            "issue-129",
            "owner/repo",
            "bounded fix",
            root=self.root,
            now=now,
        )
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        lane["status"] = "IMPLEMENTING"
        lane["last_checkpoint"] = {
            "seq": 1,
            "at": "2026-10-01T09:30:00Z",
            "claim_id": claim_id,
            "work_item": "issue-129",
            "summary": "progress",
            "decisions": [],
            "evidence_refs": [],
            "next_action": "continue",
        }
        lane["checkpoints"] = [lane["last_checkpoint"]]
        lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(manager.project(root=self.root, now=now + timedelta(hours=2, minutes=1)))
        canonical = json.loads(
            (self.root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(canonical["projection"]["checkpoint_watch"], [])

    def test_projection_is_deterministic_when_sources_do_not_change(self):
        now = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        self.assertTrue(manager.project(root=self.root, now=now))
        canonical_path = self.root / ".airlab/control-plane/canonical-state.json"
        first = json.loads(canonical_path.read_text(encoding="utf-8"))
        self.assertFalse(manager.project(root=self.root, now=now + timedelta(hours=1)))
        second = json.loads(canonical_path.read_text(encoding="utf-8"))
        self.assertEqual(first["projection"]["source_digest"], second["projection"]["source_digest"])
        self.assertEqual(first["state_revision"], second["state_revision"])


if __name__ == "__main__":
    unittest.main()
