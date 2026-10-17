"""Negative tests for prospective autonomous receipt identity binding."""
import unittest

from tools.autonomous_receipt_binding import validate_receipt_binding

IDENTITY = {
    "lane_id": "library-researcher",
    "state_version": 7,
    "claim_id": "claim-123",
    "packet_sha256": "b" * 64,
    "repository": "owner/repo",
    "pr_number": 120,
    "head_sha": "a" * 40,
}


class ReceiptBindingTests(unittest.TestCase):
    def test_exact_identity_is_only_data_validation(self):
        self.assertEqual(validate_receipt_binding(IDENTITY.copy(), IDENTITY.copy()), IDENTITY)

    def test_rejects_mismatched_or_forged_fields(self):
        changes = {
            "lane_id": "other-lane",
            "state_version": 8,
            "claim_id": "other-claim",
            "packet_sha256": "c" * 64,
            "repository": "other/repo",
            "pr_number": 121,
            "head_sha": "c" * 40,
        }
        for key, value in changes.items():
            with self.subTest(field=key), self.assertRaises(ValueError):
                validate_receipt_binding({**IDENTITY, key: value}, IDENTITY)

    def test_rejects_extra_fields_and_wrong_types(self):
        for bad in ({**IDENTITY, "trusted": True},
                    {**IDENTITY, "state_version": True},
                    {**IDENTITY, "pr_number": "120"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_receipt_binding(bad, IDENTITY)

    def test_rejects_invalid_expected_identity(self):
        for key, value in (("head_sha", "invalid"), ("packet_sha256", "bad"),
                           ("state_version", -1), ("pr_number", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_receipt_binding(IDENTITY, {**IDENTITY, key: value})


if __name__ == "__main__":
    unittest.main()
