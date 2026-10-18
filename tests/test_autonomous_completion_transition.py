"""Regression tests: autonomous transition must fail closed after valid preconditions."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tools.autonomous_completion_transition import prepare_autonomous_transition

IDENTITY = {"lane_id": "library", "state_version": 9, "claim_id": "claim",
            "packet_sha256": "b" * 64, "repository": "owner/repo",
            "pr_number": 120, "head_sha": "a" * 40}
NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def valid_lane():
    return {
        "active_claim": {"claim_id": "claim",
                         "lease_until": (NOW + timedelta(hours=1)).isoformat()},
        "review_packet": {"summary": "verified"},
        "current_gate_attestation": {"claim_id": "claim",
                                     "packet_sha256": IDENTITY["packet_sha256"]},
        "gates": {**{name: "PASS" for name in (
            "G0_CLAIM", "G1_IMPLEMENTATION", "G2_STATIC",
            "G3_CI", "G4_INTEGRATION")},
            "G5_TARGET_RUNTIME": "NOT_APPLICABLE"},
    }


class AutonomousTransitionTests(unittest.TestCase):
    def invoke(self, receipt=None, evidence=None, lane=None):
        with patch("tools.autonomous_completion_transition.derive_canonical_receipt_identity",
                   return_value=IDENTITY), patch(
                       "tools.autonomous_completion_transition._review_packet_digest",
                       return_value=IDENTITY["packet_sha256"]):
            return prepare_autonomous_transition(
                valid_lane() if lane is None else lane, {},
                IDENTITY.copy() if receipt is None else receipt,
                {"identity": IDENTITY, "trusted_receipt": False,
                 "completion_authorized": False} if evidence is None else evidence,
                now=NOW)

    def test_read_only_probe_never_authorizes(self):
        with self.assertRaisesRegex(ValueError, "authenticated autonomous completion authority"):
            self.invoke()

    def test_forged_true_flags_cannot_bypass_authentication(self):
        with self.assertRaisesRegex(ValueError, "disabled pending independent receipt authentication"):
            self.invoke(evidence={"identity": IDENTITY, "trusted_receipt": True,
                                  "completion_authorized": True})

    def test_stale_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match canonical evidence"):
            self.invoke(receipt={**IDENTITY, "state_version": 8})

    def test_runtime_evidence_required(self):
        lane = valid_lane()
        lane["gates"]["G5_TARGET_RUNTIME"] = "PENDING"
        with self.assertRaisesRegex(ValueError, "target runtime G5"):
            self.invoke(lane=lane)

    def test_expired_claim_rejected(self):
        lane = valid_lane()
        lane["active_claim"]["lease_until"] = (NOW - timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "lease expired"):
            self.invoke(lane=lane)


if __name__ == "__main__":
    unittest.main()
