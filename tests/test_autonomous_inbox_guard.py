"""Autonomous completion must never be granted by an untrusted inbox request."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tools.control_plane_inbox import _apply, OPERATIONS


class AutonomousInboxGuardTests(unittest.TestCase):
    def test_operation_is_reserved(self):
        self.assertIn("autonomous_complete", OPERATIONS)

    def test_apply_rejects_without_trusted_receipt(self):
        with patch("tools.control_plane_inbox.control_plane_manager.review_accept") as reviewer:
            with self.assertRaisesRegex(ValueError, "authenticated protected receipt"):
                _apply(None, "library", "autonomous_complete", {
                    "claim_id": "fake", "trusted_verifier_receipt": True,
                    "review_approved": True,
                }, datetime.now(timezone.utc))
            reviewer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
