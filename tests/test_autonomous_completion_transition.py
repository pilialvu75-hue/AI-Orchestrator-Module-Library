"""Regression tests: untrusted evidence cannot authorize autonomous transition."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tools.autonomous_completion_transition import prepare_autonomous_transition

IDENTITY = {"lane_id": "library", "state_version": 9, "claim_id": "claim",
            "packet_sha256": "b" * 64, "repository": "owner/repo",
            "pr_number": 120, "head_sha": "a" * 40}


class AutonomousTransitionTests(unittest.TestCase):
    @patch("tools.autonomous_completion_transition.derive_canonical_receipt_identity",
           return_value=IDENTITY)
    def test_read_only_probe_never_authorizes(self, identity):
        evidence = {"identity": IDENTITY, "trusted_receipt": False,
                    "completion_authorized": False}
        with self.assertRaisesRegex(ValueError, "authenticated autonomous completion authority"):
            prepare_autonomous_transition({}, {}, IDENTITY.copy(), evidence,
                                          now=datetime.now(timezone.utc))

    @patch("tools.autonomous_completion_transition.derive_canonical_receipt_identity",
           return_value=IDENTITY)
    def test_caller_forged_true_flags_cannot_bypass_authentication(self, identity):
        evidence = {"identity": IDENTITY, "trusted_receipt": True,
                    "completion_authorized": True}
        with self.assertRaisesRegex(ValueError, "disabled pending independent receipt authentication"):
            prepare_autonomous_transition({}, {}, IDENTITY.copy(), evidence,
                                          now=datetime.now(timezone.utc))

    @patch("tools.autonomous_completion_transition.derive_canonical_receipt_identity",
           return_value=IDENTITY)
    def test_stale_receipt_rejected(self, identity):
        evidence = {"identity": IDENTITY, "trusted_receipt": True,
                    "completion_authorized": True}
        with self.assertRaises(ValueError):
            prepare_autonomous_transition({}, {}, {**IDENTITY, "state_version": 8},
                                          evidence, now=datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
