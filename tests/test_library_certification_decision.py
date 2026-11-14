"""Security regression tests for the unsigned certification decision boundary."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_certification_decision import decide


def packet():
    return {"schema": "aivexus.library.independent-review-preflight.v1",
            "count": 1, "items": [{"asset_id": "test.asset", "decision": "BLOCKED",
            "reasons": ["PROTECTED_REVIEWER_SIGNATURE_REQUIRED"],
            "certification_authorized": False}]}


class CertificationDecisionTests(unittest.TestCase):
    def test_unsigned_remains_blocked(self):
        result = decide(packet())
        self.assertFalse(result["certification_authorized"])
        self.assertEqual(result["items"][0]["decision"], "BLOCKED")

    def test_forged_approval_flag_cannot_authorize(self):
        forged = {"verified": True, "signature_valid": True,
                  "certification_authorized": True}
        self.assertFalse(decide(packet(), forged)["certification_authorized"])

    def test_missing_and_duplicate_items_fail_closed(self):
        for invalid in ({"schema": packet()["schema"], "items": [], "count": 0},
                        {"schema": packet()["schema"], "items": packet()["items"] * 2, "count": 2}):
            with self.assertRaises(ValueError):
                decide(invalid)

    def test_preflight_cannot_claim_approved(self):
        p = packet()
        p["items"][0]["decision"] = "APPROVED"
        with self.assertRaises(ValueError):
            decide(p)


if __name__ == "__main__":
    unittest.main()
