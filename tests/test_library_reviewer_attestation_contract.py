"""Attestation metadata checks; all cases remain uncertified."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_reviewer_attestation_contract import validate_contract


def sample():
    return {"schema": "aivexus.library.reviewer-attestation.v1",
            "asset_id": "candidate.example", "source_sha256": "a" * 64,
            "evidence_sha256": "b" * 64, "reviewer_key_id": "reviewer-1",
            "issued_at": 100, "expires_at": 200, "nonce": "unique-nonce",
            "signature": "not-a-real-signature"}


class AttestationContractTests(unittest.TestCase):
    def check(self, value):
        return validate_contract(value, asset_id="candidate.example",
                                 source_sha256="a" * 64, evidence_sha256="b" * 64, now=150)

    def test_valid_metadata_never_approves(self):
        self.assertEqual(self.check(sample())["signature_verified"], False)
        self.assertFalse(self.check(sample())["certification_authorized"])

    def test_identity_digest_and_schema_mismatch(self):
        for key, bad in (("asset_id", "other"), ("source_sha256", "c" * 64),
                         ("evidence_sha256", "bad"), ("schema", "other")):
            with self.subTest(key=key):
                value = sample()
                value[key] = bad
                with self.assertRaises(ValueError):
                    self.check(value)

    def test_expired_future_and_oversized_window(self):
        for issued, expires in ((200, 300), (0, 150), (100, 100000)):
            value = sample()
            value["issued_at"], value["expires_at"] = issued, expires
            with self.assertRaises(ValueError):
                self.check(value)

    def test_missing_or_extra_fields(self):
        value = sample()
        del value["nonce"]
        with self.assertRaises(ValueError):
            self.check(value)
        value = sample()
        value["approved"] = True
        with self.assertRaises(ValueError):
            self.check(value)


if __name__ == "__main__":
    unittest.main()
