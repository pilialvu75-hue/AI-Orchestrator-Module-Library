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
            "actor_id": "chatgpt:test-cantiere",
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
            "actor_id": "chatgpt:test-cantiere",
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
            "actor_id": "chatgpt:test-cantiere",
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
            "actor_id": "chatgpt:test-cantiere",
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
            "actor_id": "chatgpt:test-main-reviewer",
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

    def test_request_requires_actor_id(self):
        lane = self._cantiere()
        request = {
            "schema_version": 1,
            "request_id": "missing-actor",
            "lane_id": "cantiere",
            "operation": "claim",
            "expected_state_version": lane["state_version"],
            "payload": {
                "work_item": "anonymous-work",
                "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
                "scope": "must fail closed",
            },
        }
        path = self._write_request(request)
        result = inbox.process_one(path, root=self.root, now=datetime(2026, 10, 1, 18, 11, tzinfo=timezone.utc))
        self.assertIn("quarantined", result)
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/quarantine/missing-actor.json").read_text(encoding="utf-8")
        )
        self.assertIn("actor_id is required", receipt["errors"][0])

    def test_unregistered_automation_is_quarantined(self):
        lane = self._cantiere()
        request = {
            "schema_version": 1,
            "request_id": "unknown-automation",
            "actor_id": "automation:unknown:deadbeef",
            "lane_id": "cantiere",
            "operation": "claim",
            "expected_state_version": lane["state_version"],
            "payload": {
                "work_item": "unknown-writer",
                "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
                "scope": "must not mutate canonical state",
            },
        }
        before = json.dumps(lane, sort_keys=True)
        path = self._write_request(request)
        result = inbox.process_one(path, root=self.root, now=datetime(2026, 10, 1, 18, 12, tzinfo=timezone.utc))
        self.assertIn("quarantined", result)
        self.assertEqual(before, json.dumps(self._cantiere(), sort_keys=True))
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/quarantine/unknown-automation.json").read_text(encoding="utf-8")
        )
        self.assertIn("not registered", receipt["errors"][0])

    def test_enabled_cantiere_lane_automation_is_owner_scoped(self):
        actor = "automation:cantiere:6abe28904d38819182462df10fe4542c"
        entry = inbox._authorize_automation_actor(
            self.root,
            actor,
            "cantiere",
            "checkpoint",
        )
        self.assertEqual(entry["owner_lane"], "cantiere")
        with self.assertRaisesRegex(ValueError, "only owner lane"):
            inbox._authorize_automation_actor(
                self.root,
                actor,
                "platform-android",
                "checkpoint",
            )

    def test_read_only_automation_cannot_mutate(self):
        with self.assertRaisesRegex(ValueError, "lacks control_plane_mutation"):
            inbox._authorize_automation_actor(
                self.root,
                "automation:library-progress:6aa541df44608191a8052bd430aca2ab",
                "library-researcher",
                "checkpoint",
            )

    def test_disabled_reviewer_automation_cannot_review_workers(self):
        actor = "automation:main-reviewer:6abe4a9283b08191af4cc91bac843616"
        for operation in ("review_accept", "record_review_gates"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "disabled by canonical registry"):
                    inbox._authorize_automation_actor(self.root, actor, "cantiere", operation)

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
            "actor_id": "chatgpt:test-cantiere",
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

    def _claimed_review_packet(self):
        now = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)
        claim_id = control_plane_manager.claim(
            "cantiere",
            "test-review-gate-recording",
            "pilialvu75-hue/Ai-orchestrator-riserva",
            "bounded review gate recording test",
            root=self.root,
            now=now,
        )
        packet = {
            "schema_version": 1,
            "submitted_at": "2026-10-09T10:01:00Z",
            "lane_id": "cantiere",
            "claim_id": claim_id,
            "work_item": "test-review-gate-recording",
            "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
            "summary": "Evidence backed gate test",
            "changes": ["bounded production change"],
            "evidence": [
                {"type": "pull_request", "ref": "https://example.test/pr/1", "result": "PASS"},
                {"type": "ci", "ref": "https://example.test/actions/1", "result": "PASS"},
                {"type": "ci", "ref": "https://example.test/actions/2", "result": "PASS"},
            ],
            "known_risks": ["target runtime not yet validated"],
            "reviewer_checks": ["review actual PR diff before approving"],
            "roadmap_impact": {"material": False, "refs": []},
        }
        packet_path = self.root / "review-packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        control_plane_manager.submit_review(
            "cantiere", packet_path, root=self.root,
            now=datetime(2026, 10, 9, 10, 2, tzinfo=timezone.utc),
        )
        return self._cantiere()

    def _gate_request(self, lane, actor="chatgpt:main-reviewer"):
        return {
            "schema_version": 1,
            "request_id": "review-gates-001",
            "actor_id": actor,
            "lane_id": "cantiere",
            "operation": "record_review_gates",
            "expected_state_version": lane["state_version"],
            "payload": {
                "summary": "Reviewer examined PR, analyzer, tests and integration",
                "evidence_indices": {
                    "G1_IMPLEMENTATION": [0],
                    "G2_STATIC": [1],
                    "G3_CI": [1],
                    "G4_INTEGRATION": [2],
                },
            },
        }

    def _external_merge_request(self, actor="chatgpt:cantiere"):
        lane = self._claimed_review_packet()
        path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane["review_packet"]["pull_request"] = 847
        path.write_text(json.dumps(lane, indent=2) + "\n", encoding="utf-8")
        return {
            "schema_version": 1,
            "request_id": "external-merge-130",
            "actor_id": actor,
            "lane_id": "cantiere",
            "operation": "reconcile_external_merge",
            "expected_state_version": lane["state_version"],
            "payload": {
                "actor_id": actor,
                "owner_directed": True,
                "claim_id": lane["active_claim"]["claim_id"],
                "pr_number": 847,
                "expected_head_sha": "a" * 40,
                "merge_commit_sha": "b" * 40,
                "packet_sha256": control_plane_manager._review_packet_digest(
                    lane["review_packet"]
                ),
            },
        }

    @staticmethod
    def _merged_pr_response():
        return {
            "number": 847, "state": "closed", "merged": True,
            "head": {"sha": "a" * 40},
            "base": {
                "ref": "main",
                "repo": {"full_name": "pilialvu75-hue/Ai-orchestrator-riserva"},
            },
            "merge_commit_sha": "b" * 40,
        }

    def test_external_merge_reconcile_archives_claim_without_review_approval(self):
        from unittest.mock import patch

        request = self._external_merge_request()
        original = self._cantiere()
        # Expired REVIEW_REQUIRED handoffs are still valid until reconciled.
        original["active_claim"]["lease_until"] = "2026-10-09T11:00:00Z"
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        lane_path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
        comparison = {
            "status": "identical", "behind_by": 0,
            "base_commit": {"sha": "b" * 40},
        }
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), patch(
            "tools.autonomous_ci_probe.fetch_json",
            side_effect=[self._merged_pr_response(), comparison],
        ) as checked:
            receipt = inbox.process_one(
                self._write_request(request),
                root=self.root,
                now=datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
            )
        self.assertIn("applied", receipt)
        self.assertEqual(checked.call_count, 2)
        changed = self._cantiere()
        self.assertEqual(changed["status"], "READY")
        self.assertIsNone(changed["active_claim"])
        self.assertNotIn("review_packet", changed)
        self.assertEqual(changed["state_version"], original["state_version"] + 1)
        self.assertEqual(changed["reviewer"]["state"], "PENDING")
        self.assertIsNone(changed["reviewer"]["reviewed_by"])
        self.assertEqual(changed["gates"]["G6_REVIEWER"], "PENDING")
        self.assertEqual(changed["gates"]["G7_CANONICAL_SYNC"], "PENDING")
        self.assertNotEqual(changed["gates"]["G5_TARGET_RUNTIME"], "PASS")
        self.assertEqual(
            changed["last_checkpoint"]["kind"], "EXTERNAL_MERGE_RECONCILIATION"
        )
        history = changed["external_merge_history"][-1]
        self.assertEqual(history["pr_number"], 847)
        self.assertEqual(history["merge_commit_sha"], "b" * 40)
        self.assertFalse(history["review_approved"])
        self.assertEqual(
            history["packet_sha256"], request["payload"]["packet_sha256"]
        )
        self.assertEqual(changed["reconciliation_events"][-1]["type"],
                         "OWNER_DIRECTED_EXTERNAL_MERGE_RECONCILED")
        self.assertEqual(
            json.loads((self.root / ".airlab/control-plane/inbox/processed/"
                        "external-merge-130.json").read_text())["status"], "APPLIED"
        )

    def test_external_merge_reconcile_rejects_unverified_or_unauthorized(self):
        from unittest.mock import patch

        for changed_field in ("unmerged", "wrong-head", "not-on-main", "actor"):
            request = self._external_merge_request(
                actor="chatgpt:other" if changed_field == "actor"
                else "chatgpt:cantiere"
            )
            request["request_id"] += "-" + changed_field
            original = self._cantiere()
            pr = self._merged_pr_response()
            comparison = {
                "status": "identical", "behind_by": 0,
                "base_commit": {"sha": "b" * 40},
            }
            if changed_field == "unmerged":
                pr["merged"] = False
            elif changed_field == "wrong-head":
                pr["head"]["sha"] = "c" * 40
            elif changed_field == "not-on-main":
                comparison["behind_by"] = 1
            with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), patch(
                "tools.autonomous_ci_probe.fetch_json",
                side_effect=[pr, comparison],
            ):
                result = inbox.process_one(
                    self._write_request(request),
                    root=self.root,
                    now=datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
                )
            self.assertIn("quarantined", result, changed_field)
            self.assertEqual(self._cantiere(), original)
            receipt_path = self.root / ".airlab/control-plane/inbox/quarantine" / (
                request["request_id"] + ".json"
            )
            self.assertEqual(json.loads(receipt_path.read_text())["status"],
                             "QUARANTINED")

    def test_review_gate_evidence_records_g1_g4_without_promoting(self):
        lane = self._claimed_review_packet()
        request = self._gate_request(lane)
        result = inbox.process_one(
            self._write_request(request), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        )
        self.assertIn("applied", result)
        changed = self._cantiere()
        self.assertEqual(changed["status"], "REVIEW_REQUIRED")
        self.assertEqual(changed["state_version"], lane["state_version"] + 1)
        for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
            self.assertEqual(changed["gates"][gate], "PASS")
        self.assertEqual(changed["gates"]["G6_REVIEWER"], "PENDING")
        self.assertEqual(changed["gates"]["G7_CANONICAL_SYNC"], "PENDING")
        attestation = changed["gate_evidence_history"][-1]
        self.assertEqual(attestation["reviewed_by"], "main-reviewer")
        self.assertEqual(attestation["evidence_refs_by_gate"]["G3_CI"], ["https://example.test/actions/1"])
        self.assertEqual(attestation["packet_sha256"], control_plane_manager._review_packet_digest(changed["review_packet"]))
        self.assertEqual(changed["current_gate_attestation"]["packet_sha256"], attestation["packet_sha256"])
        receipt = json.loads((self.root / ".airlab/control-plane/inbox/processed/review-gates-001.json").read_text())
        self.assertEqual(receipt["status"], "APPLIED")

    def test_disabled_reviewer_automation_is_quarantined_without_mutation(self):
        lane = self._claimed_review_packet()
        actor = "automation:main-reviewer:6abe4a9283b08191af4cc91bac843616"
        request = self._gate_request(lane, actor=actor)
        request["request_id"] = "review-gates-automation-001"
        result = inbox.process_one(
            self._write_request(request), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        )
        self.assertIn("quarantined", result)
        changed = self._cantiere()
        for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
            self.assertEqual(changed["gates"][gate], "PENDING")
        self.assertEqual(changed["gates"]["G6_REVIEWER"], "PENDING")
        self.assertEqual(changed["gates"]["G7_CANONICAL_SYNC"], "PENDING")

    def test_review_gate_evidence_rejects_non_reviewer_without_mutation(self):
        lane = self._claimed_review_packet()
        request = self._gate_request(lane, actor="chatgpt:cantiere")
        result = inbox.process_one(
            self._write_request(request), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        )
        self.assertIn("quarantined", result)
        self.assertEqual(self._cantiere()["gates"]["G1_IMPLEMENTATION"], "PENDING")

    def test_review_gate_evidence_rejects_wrong_type_without_mutation(self):
        lane = self._claimed_review_packet()
        request = self._gate_request(lane)
        request["payload"]["evidence_indices"]["G3_CI"] = [0]
        result = inbox.process_one(
            self._write_request(request), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        )
        self.assertIn("quarantined", result)
        self.assertEqual(self._cantiere()["gates"]["G1_IMPLEMENTATION"], "PENDING")

    def test_review_gate_evidence_rejects_stale_version(self):
        lane = self._claimed_review_packet()
        request = self._gate_request(lane)
        request["expected_state_version"] -= 1
        result = inbox.process_one(
            self._write_request(request), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        )
        self.assertIn("quarantined", result)
        self.assertEqual(self._cantiere()["gates"]["G1_IMPLEMENTATION"], "PENDING")


    def test_rework_clears_gates_and_requires_new_packet_attestation(self):
        first = self._claimed_review_packet()
        request = self._gate_request(first)
        self.assertIn("applied", inbox.process_one(
            self._write_request(request), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        ))
        control_plane_manager.review_rework(
            "cantiere", reason="Add follow-up test", next_action="Re-review changed patch.",
            root=self.root, now=datetime(2026, 10, 9, 10, 4, tzinfo=timezone.utc),
        )
        reworked = self._cantiere()
        self.assertEqual(reworked["status"], "IMPLEMENTING")
        self.assertNotIn("current_gate_attestation", reworked)
        for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
            self.assertEqual(reworked["gates"][gate], "PENDING")

        new_packet = dict(reworked["review_packet"])
        new_packet["changes"] = ["materially different replacement patch"]
        new_packet["submitted_at"] = "2026-10-09T10:05:00Z"
        packet_file = self.root / "new-review-packet.json"
        packet_file.write_text(json.dumps(new_packet), encoding="utf-8")
        control_plane_manager.submit_review(
            "cantiere", packet_file, root=self.root,
            now=datetime(2026, 10, 9, 10, 5, tzinfo=timezone.utc),
        )
        replaced = self._cantiere()
        self.assertEqual(replaced["status"], "REVIEW_REQUIRED")
        self.assertEqual(replaced["review_packet"]["changes"], new_packet["changes"])
        self.assertNotIn("current_gate_attestation", replaced)
        for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
            self.assertEqual(replaced["gates"][gate], "PENDING")
        with self.assertRaisesRegex(ValueError, "G1_IMPLEMENTATION"):
            control_plane_manager.review_accept(
                "cantiere", summary="must fail", next_action="re-review",
                root=self.root, now=datetime(2026, 10, 9, 10, 6, tzinfo=timezone.utc),
            )
        refreshed = self._gate_request(replaced)
        refreshed["request_id"] = "review-gates-after-rework"
        self.assertIn("applied", inbox.process_one(
            self._write_request(refreshed), root=self.root,
            now=datetime(2026, 10, 9, 10, 7, tzinfo=timezone.utc),
        ))
        self.assertEqual(self._cantiere()["current_gate_attestation"]["packet_sha256"],
                         control_plane_manager._review_packet_digest(new_packet))

    def test_packet_tampering_invalidates_prior_gate_attestation(self):
        first = self._claimed_review_packet()
        self.assertIn("applied", inbox.process_one(
            self._write_request(self._gate_request(first)), root=self.root,
            now=datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc),
        ))
        lane_path = self.root / ".airlab/control-plane/workstreams/cantiere.json"
        modified = self._cantiere()
        modified["review_packet"]["changes"] = ["different changes under same claim"]
        lane_path.write_text(json.dumps(modified, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale for current review packet"):
            control_plane_manager.review_accept(
                "cantiere", summary="must not pass", next_action="needs recheck",
                root=self.root, now=datetime(2026, 10, 9, 10, 4, tzinfo=timezone.utc),
            )

if __name__ == "__main__":
    unittest.main()
