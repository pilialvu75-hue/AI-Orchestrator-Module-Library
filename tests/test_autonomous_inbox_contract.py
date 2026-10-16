"""Regression contract for reviewer-free read-only preflight wiring."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = (ROOT / "tools/control_plane_inbox.py").read_text(encoding="utf-8")


class AutonomousInboxContractTests(unittest.TestCase):
    def test_single_operation_registration(self):
        section = INBOX.split("OPERATIONS =", 1)[1].split("}", 1)[0]
        self.assertEqual(section.count('"autonomous_completion_preflight"'), 1)

    def test_single_dispatch_branch(self):
        section = INBOX.split("def _apply(", 1)[1].split("def process_one(", 1)[0]
        self.assertEqual(section.count('elif operation == "autonomous_completion_preflight":'), 1)

    def test_worker_automation_authorization_is_scoped(self):
        section = INBOX.split("def process_one(", 1)[1]
        self.assertIn('automation_entry.get("kind") == "worker"', section)
        self.assertIn('automation_entry.get("owner_lane") == lane_id', section)
        self.assertIn("if not worker_chat and not authorized_worker_automation:", section)

    def test_preflight_checks_packet_identity(self):
        section = INBOX.split('elif operation == "autonomous_completion_preflight":', 1)[1]
        section = section.split('elif operation == "record_review_gates":', 1)[0]
        self.assertIn('set(payload) != {"claim_id", "packet_sha256"}', section)
        self.assertIn('payload["claim_id"] != result["claim_id"]', section)
        self.assertIn('payload["packet_sha256"] != result["packet_sha256"]', section)

    def test_preflight_is_read_only(self):
        section = INBOX.split('elif operation == "autonomous_completion_preflight":', 1)[1]
        section = section.split('elif operation == "record_review_gates":', 1)[0]
        self.assertIn("validate_autonomous_completion(lane, now=now)", section)
        self.assertNotIn("review_accept(", section)
        self.assertNotIn("lane[", section)


if __name__ == "__main__":
    unittest.main()
