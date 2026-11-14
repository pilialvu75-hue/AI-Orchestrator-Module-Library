"""Offline RSA signature verification tests; never issue certification."""
import base64
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_reviewer_signature_verify import canonical_payload, verify_signature


class SignatureTests(unittest.TestCase):
    def test_real_signature_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                            "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(p / "private.pem")],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["openssl", "pkey", "-in", str(p / "private.pem"),
                            "-pubout", "-out", str(p / "public.pem")],
                           check=True, capture_output=True, timeout=10)
            record = {"schema": "aivexus.library.reviewer-attestation.v1",
                      "asset_id": "sample", "source_sha256": "a" * 64,
                      "evidence_sha256": "b" * 64, "reviewer_key_id": "reviewer-a",
                      "issued_at": 100, "expires_at": 200, "nonce": "nonce-1"}
            (p / "payload").write_bytes(canonical_payload(record))
            subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(p / "private.pem"),
                            "-out", str(p / "sig"), str(p / "payload")],
                           check=True, capture_output=True, timeout=10)
            record["signature"] = base64.b64encode((p / "sig").read_bytes()).decode("ascii")
            public = (p / "public.pem").read_text()
            self.assertTrue(verify_signature(record, trusted_key_id="reviewer-a",
                                             trusted_public_key_pem=public))
            tampered = dict(record, source_sha256="c" * 64)
            self.assertFalse(verify_signature(tampered, trusted_key_id="reviewer-a",
                                              trusted_public_key_pem=public))
            self.assertFalse(verify_signature(record, trusted_key_id="other",
                                              trusted_public_key_pem=public))
            self.assertFalse(verify_signature(dict(record, signature="not base64!"),
                                              trusted_key_id="reviewer-a",
                                              trusted_public_key_pem=public))


if __name__ == "__main__":
    unittest.main()
