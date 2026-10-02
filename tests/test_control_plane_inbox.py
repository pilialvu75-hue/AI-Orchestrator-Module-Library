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
    "control_plane_inbox",
    ROOT / "tools" / "control_plane_inbox.py",
)
inbox = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inbox)

import control_plane_manager


class ControlPlaneInboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / ".airlab", self.root / ".airlab")

        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        lane["status"] = "READY"
        lane["active_claim"] = None
        lane["evidence"] = []
        lane.pop("review_packet", None)
        lane.pop("block_reason", None)
        lane["reviewer"] = {
            "required": True,
            "state": "PENDING",
            "reviewed_by": None,
            "reviewed_at": None,
        }
        lane["gates"].update({
            "G0_CLAIM": "PENDING",
            "G1_IMPLEMENTATION": "PENDING",
            "G2_STATIC": "PENDING",
            "G3_CI": "PENDING",
            "G4_INTEGRATION": "PENDING",
            "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE",
            "G6_REVIEWER": "PENDING",
            "G7_CANONICAL_SYNC": "PENDING",
        })
        lane_path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")

        reviewer_path = self.root / ".airlab/control-plane/workstreams/main-reviewer.json"
        reviewer = json.loads(reviewer_path.read_text(encoding="utf-8"))
        reviewer["status"] = "READY"
        reviewer["active_claim"] = None
        reviewer["evidence"] = []
        reviewer.pop("review_packet", None)
        reviewer.pop("block_reason", None)
        reviewer["gates"].update({
            "G0_CLAIM": "PENDING",
            "G1_IMPLEMENTATION": "PENDING",
            "G2_STATIC": "PENDING",
            "G3_CI": "PENDING",
            "G4_INTEGRATION": "PENDING",
            "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE",
            "G6_REVIEWER": "SELF_AUTHORITY_FOR_CROSS_LANE_REVIEW_ONLY",
            "G7_CANONICAL_SYNC": "PENDING",
        })
        reviewer_path.write_text(json.dumps(reviewer, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _write_request(self, request):
        pending = self.root / ".airlab/control-plane/inbox/pending"
        pending.mkdir(parents=True, exist_ok=True)
        path = pending / f"{request['request_id']}.json"
        path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        return path

    def _cantiere(self):
        return json.loads(
            (self.root / ".airlab/control-plane/workstreams/cantiere.json").read_text(encoding="utf-8")
        )

    def _main_reviewer(self):
        return json.loads(
            (self.root / ".airlab/control-plane/workstreams/main-reviewer.json").read_text(encoding="utf-8")
        )

    def test_valid_claim_request_applies_atomically(self):
        lane = self._cantiere()
        request = {
            "schema_version": 1,
            "request_id": "claim-001",
            "submitted_at": "2026-10-01T18:00:00Z",
            "actor_id": "automation:test-cantiere",
            "lane_id": "cantiere",
            "operation": "claim",
            "expected_state_version": lane["state_version"],
            "payload": {
                "work_item": "bounded-claim",
                "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
                "scope": "one bounded test",
                "branch": "test/bounded-claim",
                "resource_locks": ["resource:test-bounded-claim"],
            },
        }
        path = self._write_request(request)

        result = inbox.process_one(
            path,
            root=self.root,
            now=datetime(2026, 10, 1, 18, 1, tzinfo=timezone.utc),
        )

        lane = self._cantiere()
        self.assertIn("applied", result)
        self.assertEqual(lane["status"], "CLAIMED")
        self.assertEqual(lane["active_claim"]["work_item"], "bounded-claim")
        self.assertEqual(
            lane["active_claim"]["resource_locks"],
            [
                "branch:pilialvu75-hue/Ai-orchestrator-riserva:test/bounded-claim",
                "resource:test-bounded-claim",
            ],
        )
        self.assertEqual(lane["state_version"], request["expected_state_version"] + 1)
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/processed/claim-001.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["status"], "APPLIED")
        self.assertFalse(path.exists())

    def test_stale_expected_version_is_quarantined_without_mutating_lane(self):
        lane = self._cantiere()
        before = json.dumps(lane, sort_keys=True)
        request = {
            "schema_version": 1,
            "request_id": "stale-001",
            "lane_id": "cantiere",
            "operation": "claim",
            "expected_state_version": lane["state_version"] - 1,
            "payload": {
                "work_item": "stale-work",
                "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
                "scope": "stale request",
            },
        }
        path = self._write_request(request)

        result = inbox.process_one(
            path,
            root=self.root,
            now=datetime(2026, 10, 1, 18, 2, tzinfo=timezone.utc),
        )

        after = json.dumps(self._cantiere(), sort_keys=True)
        self.assertIn("quarantined", result)
        self.assertEqual(before, after)
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/quarantine/stale-001.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["status"], "QUARANTINED")
        self.assertIn("state_version conflict", receipt["errors"][0])

    def test_invalid_candidate_is_quarantined_without_corrupting_lane(self):
        lane = self._cantiere()
        before = json.dumps(lane, sort_keys=True)
        request = {
            "schema_version": 1,
            "request_id": "scope-001",
            "lane_id": "cantiere",
            "operation": "claim",
            "expected_state_version": lane["state_version"],
            "payload": {
                "work_item": "wrong-repo",
                "repository": "owner/not-allowed",
                "scope": "should be rejected",
            },
        }
        path = self._write_request(request)

        result = inbox.process_one(
            path,
            root=self.root,
            now=datetime(2026, 10, 1, 18, 3, tzinfo=timezone.utc),
        )

        self.assertIn("quarantined", result)
        self.assertEqual(before, json.dumps(self._cantiere(), sort_keys=True))
        self.assertTrue(
            (self.root / ".airlab/control-plane/inbox/quarantine/scope-001.json").exists()
        )

    def test_cross_lane_resource_race_quarantines_second_request(self):
        cantiere = self._cantiere()
        reviewer = self._main_reviewer()
        first = {
            "schema_version": 1,
            "request_id": "race-cantiere",
            "lane_id": "cantiere",
            "operation": "claim",
            "expected_state_version": cantiere["state_version"],
            "payload": {
                "work_item": "race-worker-a",
                "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
                "scope": "first serialized writer",
                "resource_locks": ["contract:shared-runtime"],
            },
        }
        second = {
            "schema_version": 1,
            "request_id": "race-reviewer",
            "lane_id": "main-reviewer",
            "operation": "claim",
            "expected_state_version": reviewer["state_version"],
            "payload": {
                "work_item": "race-worker-b",
                "repository": "pilialvu75-hue/AI-Orchestrator-Module-Library",
                "scope": "different work item but same shared contract",
                "resource_locks": ["contract:shared-runtime"],
            },
        }
        first_path = self._write_request(first)
        second_path = self._write_request(second)

        first_result = inbox.process_one(
            first_path,
            root=self.root,
            now=datetime(2026, 10, 1, 18, 10, tzinfo=timezone.utc),
        )
        second_result = inbox.process_one(
            second_path,
            root=self.root,
            now=datetime(2026, 10, 1, 18, 10, tzinfo=timezone.utc),
        )

        self.assertIn("applied", first_result)
        self.assertIn("quarantined", second_result)
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/quarantine/race-reviewer.json").read_text(encoding="utf-8")
        )
        self.assertIn("resource lock conflict", receipt["errors"][0])
        self.assertIsNone(self._main_reviewer()["active_claim"])
        self.assertEqual(
            self._cantiere()["active_claim"]["resource_locks"],
            ["contract:shared-runtime"],
        )

    def test_unreadable_unrelated_lane_does_not_blind_healthy_checkpoint(self):
        now = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
        claim_id = control_plane_manager.claim(
            "cantiere",
            "healthy-checkpoint",
            "pilialvu75-hue/Ai-orchestrator-riserva",
            "checkpoint despite unrelated broken lane",
            root=self.root,
            now=now,
        )
        lane = self._cantiere()
        broken_path = self.root / ".airlab/control-plane/workstreams/voice-live.json"
        broken_path.write_text("{not-json", encoding="utf-8")

        request = {
            "schema_version": 1,
            "request_id": "checkpoint-001",
            "lane_id": "cantiere",
            "operation": "checkpoint",
            "expected_state_version": lane["state_version"],
            "payload": {
                "summary": "Healthy lane still progresses.",
                "next_action": "Continue bounded work.",
                "decisions": [],
                "evidence_refs": ["claim:" + claim_id],
            },
        }
        path = self._write_request(request)

        result = inbox.process_one(
            path,
            root=self.root,
            now=datetime(2026, 10, 1, 18, 5, tzinfo=timezone.utc),
        )

        self.assertIn("applied", result)
        lane = self._cantiere()
        self.assertEqual(lane["status"], "IMPLEMENTING")
        self.assertEqual(lane["last_checkpoint"]["summary"], "Healthy lane still progresses.")
        canonical = json.loads(
            (self.root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8")
        )
        incidents = canonical["projection"]["projection_incidents"]
        self.assertTrue(any(item["path"].endswith("voice-live.json") for item in incidents))


if __name__ == "__main__":
    unittest.main()
