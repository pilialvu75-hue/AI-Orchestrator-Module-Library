import hashlib
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
    "canonical_sync_receipts",
    ROOT / "tools" / "canonical_sync_receipts.py",
)
receipts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receipts)


class CanonicalSyncReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / ".airlab", self.root / ".airlab")
        for folder in ("pending", "processed", "quarantine"):
            (self.root / ".airlab/control-plane/inbox" / folder).mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / ".airlab/control-plane/canonical-sync-receipts.json"
        self.registry_path.write_text(json.dumps({
            "schema_version": 1,
            "policy": {
                "mode": "evidence_backed_before_after_digest",
                "material_sync_only": True,
                "require_content_change": True,
                "require_evidence_ref": True,
                "enforcement_started_at": None,
            },
            "records": [],
        }, indent=2) + "\n", encoding="utf-8")
        self.lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(self.lane_path.read_text(encoding="utf-8"))
        lane["status"] = "REVIEW_REQUIRED"
        lane["state_version"] = 10
        lane["active_claim"] = {
            "claim_id": "claim-roadmap-1",
            "owner_lane": "cantiere",
            "work_item": "material-roadmap-change",
            "repository": "owner/repo",
            "scope": "bounded",
            "branch": "feature/material-roadmap-change",
            "resource_locks": [],
            "lease_until": "2026-10-04T00:00:00Z",
        }
        lane["review_packet"] = {
            "schema_version": 1,
            "submitted_at": "2026-10-03T16:00:00Z",
            "lane_id": "cantiere",
            "claim_id": "claim-roadmap-1",
            "work_item": "material-roadmap-change",
            "repository": "owner/repo",
            "summary": "Material change.",
            "changes": ["Changed behavior."],
            "evidence": [{"type": "test", "ref": "unit", "result": "PASS"}],
            "known_risks": [],
            "reviewer_checks": ["Check roadmap sync."],
            "roadmap_impact": {"material": True, "refs": [".airlab/roadmap.yaml#L1"]},
        }
        lane.setdefault("gates", {})["G7_CANONICAL_SYNC"] = "PENDING"
        lane.setdefault("reviewer", {})["reviewed_at"] = None
        self.lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _pending(self, request_id, operation, expected, payload):
        path = self.root / ".airlab/control-plane/inbox/pending" / f"{request_id}.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "request_id": request_id,
            "actor_id": "chatgpt:test",
            "lane_id": "cantiere",
            "operation": operation,
            "expected_state_version": expected,
            "payload": payload,
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _capture_baseline(self):
        path = self._pending("review-accept-1", "review_accept", 10, {
            "summary": "Accepted.",
            "next_action": "Sync roadmap.",
            "evidence_refs": ["PR #1"],
        })
        outcomes = receipts.prepare(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(outcomes, [])
        self.assertTrue(path.exists())
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(registry["policy"]["enforcement_started_at"])
        self.assertEqual(registry["records"][0]["status"], "BASELINE_CAPTURED")
        return registry["records"][0]["roadmap_refs"][0]["before_sha256"]

    def _set_blocked(self):
        lane = json.loads(self.lane_path.read_text(encoding="utf-8"))
        lane["status"] = "BLOCKED"
        lane["state_version"] = 11
        lane["active_claim"] = None
        lane["block_reason"] = {
            "code": "CANONICAL_SYNC_REQUIRED",
            "roadmap_refs": [".airlab/roadmap.yaml#L1"],
            "reviewed_claim_id": "claim-roadmap-1",
            "work_item": "material-roadmap-change",
            "detected_at": "2026-10-03T16:31:00Z",
        }
        lane["gates"]["G7_CANONICAL_SYNC"] = "PENDING_ROADMAP_SYNC"
        lane["reviewer"]["reviewed_at"] = "2026-10-03T16:31:00Z"
        self.lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

    def _change_roadmap(self):
        path = self.root / ".airlab/roadmap.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "\n# receipt-test-change\n", encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_review_accept_material_captures_pre_sync_digest(self):
        before = self._capture_baseline()
        actual = hashlib.sha256((self.root / ".airlab/roadmap.yaml").read_bytes()).hexdigest()
        self.assertEqual(before, actual)

    def test_completion_without_receipts_is_quarantined(self):
        self._capture_baseline()
        self._set_blocked()
        path = self._pending("sync-missing-receipts", "canonical_sync_complete", 11, {
            "refs": [".airlab/roadmap.yaml#L1"]
        })
        outcomes = receipts.prepare(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 35, tzinfo=timezone.utc),
        )
        self.assertTrue(any("quarantined" in item for item in outcomes))
        self.assertFalse(path.exists())
        self.assertTrue((self.root / ".airlab/control-plane/inbox/quarantine/sync-missing-receipts.json").exists())

    def test_unchanged_material_roadmap_is_quarantined(self):
        before = self._capture_baseline()
        self._set_blocked()
        path = self._pending("sync-unchanged", "canonical_sync_complete", 11, {
            "refs": [".airlab/roadmap.yaml#L1"],
            "receipts": [{
                "ref": ".airlab/roadmap.yaml#L1",
                "before_sha256": before,
                "after_sha256": before,
                "evidence_ref": "commit:abc123",
            }],
        })
        outcomes = receipts.prepare(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 35, tzinfo=timezone.utc),
        )
        self.assertTrue(any("did not change" in item for item in outcomes))
        self.assertFalse(path.exists())

    def test_wrong_before_digest_is_quarantined(self):
        self._capture_baseline()
        self._set_blocked()
        after = self._change_roadmap()
        path = self._pending("sync-wrong-before", "canonical_sync_complete", 11, {
            "refs": [".airlab/roadmap.yaml#L1"],
            "receipts": [{
                "ref": ".airlab/roadmap.yaml#L1",
                "before_sha256": "0" * 64,
                "after_sha256": after,
                "evidence_ref": "commit:abc123",
            }],
        })
        outcomes = receipts.prepare(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 35, tzinfo=timezone.utc),
        )
        self.assertTrue(any("captured baseline" in item for item in outcomes))
        self.assertFalse(path.exists())

    def test_valid_receipt_finalizes_after_applied_g7(self):
        before = self._capture_baseline()
        self._set_blocked()
        after = self._change_roadmap()
        pending = self._pending("sync-valid", "canonical_sync_complete", 11, {
            "refs": [".airlab/roadmap.yaml#L1"],
            "receipts": [{
                "ref": ".airlab/roadmap.yaml#L1",
                "before_sha256": before,
                "after_sha256": after,
                "evidence_ref": "commit:abc123",
            }],
        })
        outcomes = receipts.prepare(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 35, tzinfo=timezone.utc),
        )
        self.assertEqual(outcomes, [])
        pending.unlink()
        processed = self.root / ".airlab/control-plane/inbox/processed/sync-valid.json"
        processed.write_text(json.dumps({
            "schema_version": 1,
            "request_id": "sync-valid",
            "status": "APPLIED",
            "result_state_version": 12,
        }), encoding="utf-8")
        lane = json.loads(self.lane_path.read_text(encoding="utf-8"))
        lane["status"] = "READY"
        lane["state_version"] = 12
        lane.pop("block_reason", None)
        lane["gates"]["G7_CANONICAL_SYNC"] = "PASS"
        self.lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        outcomes = receipts.finalize(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 36, tzinfo=timezone.utc),
        )
        self.assertTrue(any("reconciled" in item for item in outcomes))
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(registry["records"][0]["status"], "RECONCILED")
        self.assertEqual(registry["records"][0]["completion"]["receipts"][0]["after_sha256"], after)
        self.assertEqual(receipts.check(root=self.root), [])

    def test_direct_g7_bypass_after_enforcement_fails_check(self):
        self._capture_baseline()
        lane = json.loads(self.lane_path.read_text(encoding="utf-8"))
        lane["status"] = "READY"
        lane["active_claim"] = None
        lane["gates"]["G7_CANONICAL_SYNC"] = "PASS"
        lane["reviewer"]["reviewed_at"] = "2026-10-03T16:31:00Z"
        self.lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        errors = receipts.check(root=self.root)
        self.assertTrue(any("requires finalized evidence-backed" in error for error in errors))

    def test_pre_enforcement_material_g7_is_grandfathered(self):
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        registry["policy"]["enforcement_started_at"] = "2026-10-03T17:00:00Z"
        self.registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        lane = json.loads(self.lane_path.read_text(encoding="utf-8"))
        lane["active_claim"] = None
        lane["status"] = "READY"
        lane["gates"]["G7_CANONICAL_SYNC"] = "PASS"
        lane["reviewer"]["reviewed_at"] = "2026-10-03T16:00:00Z"
        self.lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        self.assertEqual(receipts.check(root=self.root), [])


if __name__ == "__main__":
    unittest.main()
