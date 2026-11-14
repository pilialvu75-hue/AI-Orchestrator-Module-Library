"""Verify both source binding and real signatures; never authorize."""
import base64
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_reviewer_attestation_verify import verify_attestation
from library_reviewer_signature_verify import canonical_payload


class CombinedAttestationTests(unittest.TestCase):
    def test_valid_signature_is_not_certification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                            "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(root / "priv.pem")],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["openssl", "pkey", "-in", str(root / "priv.pem"),
                            "-pubout", "-out", str(root / "pub.pem")],
                           check=True, capture_output=True, timeout=10)
            record = {"schema": "aivexus.library.reviewer-attestation.v1",
                      "asset_id": "asset.one", "source_sha256": "a" * 64,
                      "evidence_sha256": "b" * 64, "reviewer_key_id": "trusted-1",
                      "issued_at": 100, "expires_at": 200, "nonce": "unique-1"}
            (root / "payload").write_bytes(canonical_payload(record))
            subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(root / "priv.pem"),
                            "-out", str(root / "sig"), str(root / "payload")],
                           check=True, capture_output=True, timeout=10)
            record["signature"] = base64.b64encode((root / "sig").read_bytes()).decode()
            args = {"asset_id": "asset.one", "source_sha256": "a" * 64,
                    "evidence_sha256": "b" * 64, "now": 150,
                    "trusted_key_id": "trusted-1",
                    "trusted_public_key_pem": (root / "pub.pem").read_text()}
            verified = verify_attestation(record, **args)
            self.assertTrue(verified["signature_verified"])
            self.assertFalse(verified["certification_authorized"])
            with self.assertRaisesRegex(ValueError, "mismatch"):
                verify_attestation(record, **dict(args, source_sha256="c" * 64))
            with self.assertRaisesRegex(ValueError, "validity"):
                verify_attestation(record, **dict(args, now=201))
            self.assertFalse(verify_attestation(record, **dict(args, trusted_key_id="other"))["signature_verified"])


if __name__ == "__main__":
    unittest.main()
