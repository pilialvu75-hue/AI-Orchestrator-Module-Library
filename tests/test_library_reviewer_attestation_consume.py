"""End-to-end local verification and replay rejection."""
import base64
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_reviewer_attestation_consume import verify_and_reserve
from library_reviewer_signature_verify import canonical_payload


class ConsumeTests(unittest.TestCase):
    def test_valid_once_tampered_never_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ledger").mkdir()
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                            "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(root / "priv")],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["openssl", "pkey", "-in", str(root / "priv"),
                            "-pubout", "-out", str(root / "pub")],
                           check=True, capture_output=True, timeout=10)
            record = {"schema": "aivexus.library.reviewer-attestation.v1",
                      "asset_id": "asset", "source_sha256": "a" * 64,
                      "evidence_sha256": "b" * 64, "reviewer_key_id": "reviewer",
                      "issued_at": 100, "expires_at": 200, "nonce": "unique"}
            (root / "payload").write_bytes(canonical_payload(record))
            subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(root / "priv"),
                            "-out", str(root / "sig"), str(root / "payload")],
                           check=True, capture_output=True, timeout=10)
            record["signature"] = base64.b64encode((root / "sig").read_bytes()).decode()
            args = dict(asset_id="asset", source_sha256="a" * 64,
                        evidence_sha256="b" * 64, now=150, trusted_key_id="reviewer",
                        trusted_public_key_pem=(root / "pub").read_text(),
                        ledger_dir=root / "ledger")
            first = verify_and_reserve(record, **args)
            self.assertTrue(first["signature_verified"])
            self.assertTrue(first["nonce_reserved"])
            self.assertFalse(first["certification_authorized"])
            second = verify_and_reserve(record, **args)
            self.assertFalse(second["nonce_reserved"])
            tampered = dict(record, signature="invalid!")
            self.assertFalse(verify_and_reserve(tampered, **args)["nonce_reserved"])
            self.assertEqual(len(list((root / "ledger").iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
