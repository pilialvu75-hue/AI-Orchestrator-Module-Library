import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WAIT_SPEC = importlib.util.spec_from_file_location(
    "control_plane_wait_inbox",
    ROOT / "tools" / "control_plane_wait_inbox.py",
)
wait_inbox = importlib.util.module_from_spec(WAIT_SPEC)
WAIT_SPEC.loader.exec_module(wait_inbox)
manager = wait_inbox.control_plane_manager


class ControlPlaneWaitInboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".airlab/control-plane/workstreams").mkdir(parents=True)
        (self.root / ".airlab/control-plane/inbox/pending").mkdir(parents=True)
        (self.root / ".airlab/control-plane/inbox/processed").mkdir(parents=True)
        (self.root / ".airlab/control-plane/inbox/quarantine").mkdir(parents=True)

        for rel in [
            ".airlab/control-plane/gates.json",
            ".airlab/control-plane/inference-policy.json",
            ".airlab/control-plane/chat-registry.json",
            ".airlab/control-plane/automation-registry.json",
            ".airlab/control-plane/historical-chat-consolidation.json",
        ]:
            src = ROOT / rel
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

        canonical = json.loads((ROOT / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
        self.paths = [
            ".airlab/control-plane/workstreams/main-reviewer.json",
            ".airlab/control-plane/workstreams/cantiere.json",
        ]
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
            shutil.copyfile(src, dst)
            lane = json.loads(dst.read_text(encoding="utf-8"))
            lane["status"] = "READY"
            lane["active_claim"] = None
            lane.pop("wait_state", None)
            lane.pop("block_reason", None)
            lane.setdefault("gates", {})["G0_CLAIM"] = "PENDING"
            if lane.get("role") != "reviewer":
                lane.setdefault("reviewer", {})["state"] = "PENDING"
            dst.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

        registry = json.loads((self.root / ".airlab/control-plane/chat-registry.json").read_text(encoding="utf-8"))
        for entry in registry["lanes"]:
            if entry["id"] in {"main-reviewer", "cantiere"}:
                entry["primary_repository"] = "owner/repo"
                entry["secondary_repositories"] = []
        registry["lanes"] = [entry for entry in registry["lanes"] if entry["id"] in {"main-reviewer", "cantiere"}]
        (self.root / ".airlab/control-plane/chat-registry.json").write_text(
            json.dumps(registry, indent=2) + "\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def _claim_cantiere(self, now):
        return manager.claim(
            "cantiere",
            "physical-retest",
            "owner/repo",
            "bounded physical acceptance",
            branch="feature/physical-retest",
            resource_locks=["contract:cantiere-lifecycle", "resource:manga-acceptance"],
            root=self.root,
            now=now,
        )

    def _request(self, request_id, lane_id, operation, expected, payload):
        path = self.root / ".airlab/control-plane/inbox/pending" / f"{request_id}.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "request_id": request_id,
            "actor_id": "chatgpt:test",
            "lane_id": lane_id,
            "operation": operation,
            "expected_state_version": expected,
            "payload": payload,
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_enter_wait_releases_lease_but_preserves_reservations(self):
        now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
        claim_id = self._claim_cantiere(now)
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        path = self._request(
            "wait-enter",
            "cantiere",
            "enter_wait",
            lane["state_version"],
            {
                "wait_type": "WAITING_OWNER",
                "resume_condition": "owner completes physical device retest",
                "summary": "Implementation is ready for physical acceptance.",
                "next_action": "Resume only when physical evidence arrives.",
                "evidence_refs": ["PR #745"],
            },
        )
        result = wait_inbox.process_wait_request(path, root=self.root, now=now + timedelta(minutes=5))
        self.assertIn("applied", result)
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        self.assertEqual(lane["status"], "BLOCKED")
        self.assertIsNone(lane["active_claim"])
        self.assertEqual(lane["wait_state"]["prior_claim_id"], claim_id)
        self.assertEqual(lane["wait_state"]["type"], "WAITING_OWNER")
        self.assertIn("contract:cantiere-lifecycle", lane["wait_state"]["resource_locks"])
        projection = json.loads((self.root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))["projection"]
        self.assertFalse(any(item["lane"] == "cantiere" for item in projection["active_claims"]))
        self.assertFalse(any(item["lane"] == "cantiere" for item in projection["checkpoint_watch"]))

    def test_resume_wait_requires_signal_and_evidence_then_returns_ready_without_claim(self):
        now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
        self._claim_cantiere(now)
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        enter = self._request("wait-enter-2", "cantiere", "enter_wait", lane["state_version"], {
            "wait_type": "WAITING_EXTERNAL",
            "resume_condition": "CI artifact becomes available",
            "summary": "Waiting for external artifact.",
            "next_action": "Claim a bounded validation item after resume.",
        })
        wait_inbox.process_wait_request(enter, root=self.root, now=now + timedelta(minutes=1))
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        bad = self._request("wait-resume-bad", "cantiere", "resume_wait", lane["state_version"], {
            "signal_id": "artifact-ready",
            "evidence_refs": [],
        })
        result = wait_inbox.process_wait_request(bad, root=self.root, now=now + timedelta(minutes=2))
        self.assertIn("quarantined", result)
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        good = self._request("wait-resume-good", "cantiere", "resume_wait", lane["state_version"], {
            "signal_id": "artifact-ready",
            "evidence_refs": ["run:123"],
        })
        result = wait_inbox.process_wait_request(good, root=self.root, now=now + timedelta(minutes=3))
        self.assertIn("applied", result)
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        self.assertEqual(lane["status"], "READY")
        self.assertIsNone(lane["active_claim"])
        self.assertNotIn("wait_state", lane)
        self.assertEqual(lane["wait_history"][-1]["signal_id"], "artifact-ready")

    def test_wait_reservation_quarantines_different_work_item_using_same_resource(self):
        now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
        self._claim_cantiere(now)
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        enter = self._request("wait-enter-3", "cantiere", "enter_wait", lane["state_version"], {
            "wait_type": "WAITING_OWNER",
            "resume_condition": "owner retest",
            "summary": "Waiting on owner.",
            "next_action": "Resume from evidence.",
        })
        wait_inbox.process_wait_request(enter, root=self.root, now=now + timedelta(minutes=1))
        main_lane = json.loads((self.root / ".airlab/control-plane/workstreams/main-reviewer.json").read_text(encoding="utf-8"))
        claim_path = self._request("conflicting-claim", "main-reviewer", "claim", main_lane["state_version"], {
            "work_item": "different-name",
            "repository": "owner/repo",
            "scope": "conflicting shared contract",
            "resource_locks": ["contract:cantiere-lifecycle"],
        })
        outcomes = wait_inbox.preflight_claim_requests(root=self.root, now=now + timedelta(minutes=2))
        self.assertTrue(any("conflicting-claim" in item and "quarantined" in item for item in outcomes))
        self.assertFalse(claim_path.exists())
        receipt = json.loads((self.root / ".airlab/control-plane/inbox/quarantine/conflicting-claim.json").read_text(encoding="utf-8"))
        self.assertIn("wait reservation conflict", receipt["errors"][0])

    def test_wait_reservation_allows_safe_parallel_claim(self):
        now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
        self._claim_cantiere(now)
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        enter = self._request("wait-enter-4", "cantiere", "enter_wait", lane["state_version"], {
            "wait_type": "WAITING_EXTERNAL",
            "resume_condition": "artifact arrives",
            "summary": "Waiting externally.",
            "next_action": "Resume when artifact arrives.",
        })
        wait_inbox.process_wait_request(enter, root=self.root, now=now + timedelta(minutes=1))
        main_lane = json.loads((self.root / ".airlab/control-plane/workstreams/main-reviewer.json").read_text(encoding="utf-8"))
        claim_path = self._request("safe-claim", "main-reviewer", "claim", main_lane["state_version"], {
            "work_item": "independent-control-plane-work",
            "repository": "owner/repo",
            "scope": "unrelated file",
            "resource_locks": ["file:owner/repo:tools/unrelated.py"],
        })
        wait_inbox.preflight_claim_requests(root=self.root, now=now + timedelta(minutes=2))
        self.assertTrue(claim_path.exists())

    def test_expired_claim_cannot_enter_wait(self):
        now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
        self._claim_cantiere(now)
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        path = self._request("expired-wait", "cantiere", "enter_wait", lane["state_version"], {
            "wait_type": "WAITING_EXTERNAL",
            "resume_condition": "external input",
            "summary": "Too late.",
            "next_action": "Reviewer reconcile first.",
        })
        result = wait_inbox.process_wait_request(path, root=self.root, now=now + timedelta(hours=13))
        self.assertIn("quarantined", result)
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(lane["active_claim"])
        self.assertNotIn("wait_state", lane)


if __name__ == "__main__":
    unittest.main()
