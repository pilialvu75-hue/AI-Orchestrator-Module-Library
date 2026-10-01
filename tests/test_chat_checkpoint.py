import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "chat_checkpoint",
    ROOT / "tools" / "chat_checkpoint.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ChatCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".airlab/control-plane/workstreams").mkdir(parents=True)
        canonical = json.loads((ROOT / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
        target_rel = ".airlab/control-plane/workstreams/cantiere.json"
        canonical["workstreams"] = [target_rel]
        (self.root / ".airlab/control-plane/canonical-state.json").write_text(
            json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
        )
        src = ROOT / target_rel
        dst = self.root / target_rel
        shutil.copyfile(src, dst)
        lane = json.loads(dst.read_text(encoding="utf-8"))
        lane["status"] = "CLAIMED"
        lane["active_claim"] = {
            "claim_id": "claim-1",
            "owner_lane": "cantiere",
            "work_item": "work-1",
            "repository": "owner/repo",
            "scope": "bounded",
            "branch": "fix/work-1",
            "started_at": "2026-10-01T08:00:00Z",
            "heartbeat_at": "2026-10-01T08:00:00Z",
            "lease_until": "2026-10-01T20:00:00Z",
            "lease_hours": 12,
        }
        lane["checkpoints"] = []
        lane.pop("last_checkpoint", None)
        dst.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_checkpoint_persists_progress_and_renews_claim(self):
        now = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        result = module.checkpoint(
            "cantiere",
            "Fixed reviewer boundary.",
            "Run target test.",
            decisions=["Keep shared contract."],
            evidence_refs=["PR #123"],
            root=self.root,
            now=now,
        )
        lane = json.loads(
            (self.root / ".airlab/control-plane/workstreams/cantiere.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result["seq"], 1)
        self.assertEqual(lane["status"], "IMPLEMENTING")
        self.assertEqual(lane["last_checkpoint"]["summary"], "Fixed reviewer boundary.")
        self.assertEqual(lane["next_action"], "Run target test.")
        self.assertEqual(lane["active_claim"]["heartbeat_at"], "2026-10-01T10:00:00Z")
        self.assertEqual(lane["active_claim"]["lease_until"], "2026-10-01T22:00:00Z")

    def test_checkpoint_ignores_unreadable_unrelated_lane(self):
        canonical_path = self.root / ".airlab/control-plane/canonical-state.json"
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        broken_rel = ".airlab/control-plane/workstreams/broken.json"
        canonical["workstreams"] = [broken_rel] + canonical["workstreams"]
        canonical_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
        broken_path = self.root / broken_rel
        broken_path.parent.mkdir(parents=True, exist_ok=True)
        broken_path.write_text("{not-json", encoding="utf-8")

        result = module.checkpoint(
            "cantiere",
            "Healthy checkpoint.",
            "Continue.",
            root=self.root,
            now=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(result["summary"], "Healthy checkpoint.")

    def test_checkpoint_rejects_expired_claim(self):
        path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(path.read_text(encoding="utf-8"))
        lane["active_claim"]["lease_until"] = "2026-10-01T09:00:00Z"
        path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expired claim"):
            module.checkpoint(
                "cantiere",
                "summary",
                "next",
                root=self.root,
                now=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
            )

    def test_checkpoint_requires_active_claim(self):
        path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(path.read_text(encoding="utf-8"))
        lane["active_claim"] = None
        lane["status"] = "READY"
        path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no active claim"):
            module.checkpoint(
                "cantiere",
                "summary",
                "next",
                root=self.root,
                now=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
