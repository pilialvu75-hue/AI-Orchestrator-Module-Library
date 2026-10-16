"""Negative tests for read-only autonomous completion eligibility."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import unittest

from tools.control_plane_manager import validate_autonomous_completion


def eligible_lane():
    now = datetime.now(timezone.utc)
    claim = {
        "claim_id": "claim-1", "work_item": "item-1", "repository": "owner/repo",
        "lease_until": (now + timedelta(hours=2)).isoformat(),
    }
    packet = {
        "schema_version": 1, "submitted_at": now.isoformat(),
        "lane_id": "library-researcher", "claim_id": "claim-1",
        "work_item": "item-1", "repository": "owner/repo",
        "summary": "verified work", "changes": ["bounded change"],
        "evidence": [{"type": "test", "ref": "tests/test_example.py", "result": "PASS"}],
        "known_risks": [], "reviewer_checks": ["static and CI evidence"],
        "roadmap_impact": {"material": False, "refs": []},
    }
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return {
        "id": "library-researcher", "role": "worker", "status": "REVIEW_REQUIRED",
        "state_version": 7, "active_claim": claim, "review_packet": packet,
        "gates": {**{g: "PASS" for g in ("G0_CLAIM", "G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION")},
                  "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE"},
        "current_gate_attestation": {"claim_id": "claim-1", "packet_sha256": digest, "verified_by": "automation:independent-verifier"},
    }


def test_preflight_does_not_mutate_lane():
    lane = eligible_lane()
    original = copy.deepcopy(lane)
    result = validate_autonomous_completion(lane)
    assert result["state_version"] == 7
    assert result["eligible_for_transactional_processing"] is True
    assert lane == original


class AutonomousCompletionTests(unittest.TestCase):
    def test_preflight_fails_closed(self):
        changes = [
    lambda lane: lane.update(status="IMPLEMENTING"),
    lambda lane: lane.update(active_claim=None),
    lambda lane: lane["gates"].update(G3_CI="PENDING"),
    lambda lane: lane["gates"].update(G5_TARGET_RUNTIME="UNKNOWN"),
    lambda lane: lane["current_gate_attestation"].update(packet_sha256="stale"),
    lambda lane: lane["current_gate_attestation"].update(claim_id="other-claim"),
    lambda lane: lane["current_gate_attestation"].pop("verified_by"),
    lambda lane: lane["current_gate_attestation"].update(verified_by="chatgpt:library-researcher"),
    lambda lane: lane["review_packet"].update(summary="changed after attestation"),
    lambda lane: lane["gates"].update(G2_STATIC="UNKNOWN"),
    lambda lane: lane["gates"].update(G4_INTEGRATION="PENDING"),
    lambda lane: lane["review_packet"].update(claim_id="wrong"),
    lambda lane: lane.update(state_version=None),
    lambda lane: lane.update(role="reviewer"),
    lambda lane: lane["review_packet"]["evidence"].clear(),
    lambda lane: lane["review_packet"]["changes"].clear(),
    lambda lane: lane["review_packet"]["roadmap_impact"].pop("refs"),
]
        for change in changes:
            with self.subTest(change=repr(change)):
                lane = eligible_lane()
                change(lane)
                with self.assertRaises(ValueError):
                    validate_autonomous_completion(lane)


def test_preflight_rejects_expired_claim():
    lane = eligible_lane()
    lane["active_claim"]["lease_until"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with unittest.TestCase().assertRaises(ValueError):
        validate_autonomous_completion(lane)


class AutonomousPreflightTests(unittest.TestCase):
    def test_valid(self):
        test_preflight_does_not_mutate_lane()

    def test_invalid(self):
        AutonomousCompletionTests().test_preflight_fails_closed()

    def test_expired(self):
        test_preflight_rejects_expired_claim()
