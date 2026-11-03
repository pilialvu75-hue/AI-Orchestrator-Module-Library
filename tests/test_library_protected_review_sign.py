import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_protected_review_sign import sign


def statement():
    return {"schema": "ai-orchestrator.library-review-authorization.v1",
            "asset_id": "demo.external", "version": "0.1.0",
            "source_commit": "a" * 40, "payload_sha256": "b" * 64,
            "sbom_sha256": "c" * 64, "license_file_sha256": "d" * 64,
            "reviewed_at": "2026-11-03T00:00:00Z", "reviewer_id": "independent-reviewer",
            "known_vulnerabilities": 0, "decision": "APPROVED"}


class ProtectedSignerTests(unittest.TestCase):
    def test_missing_protected_key_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "protected signing key unavailable"):
            sign(statement(), "")

    def test_unapproved_decision_cannot_be_signed(self):
        item = statement()
        item["decision"] = "BLOCKED"
        with self.assertRaisesRegex(ValueError, "has not approved"):
            sign(item, "")

    def test_known_vulnerability_cannot_be_signed(self):
        item = statement()
        item["known_vulnerabilities"] = 1
        with self.assertRaisesRegex(ValueError, "zero-known-vulnerability"):
            sign(item, "")

    def test_source_digest_required(self):
        item = statement()
        item["payload_sha256"] = "not-pinned"
        with self.assertRaisesRegex(ValueError, "source-bound"):
            sign(item, "")

    def test_unexpected_fields_rejected(self):
        item = statement()
        item["override"] = True
        with self.assertRaisesRegex(ValueError, "fields mismatch"):
            sign(item, "")


if __name__ == "__main__":
    unittest.main()
