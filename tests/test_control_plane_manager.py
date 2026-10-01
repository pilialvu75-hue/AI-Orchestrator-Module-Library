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
