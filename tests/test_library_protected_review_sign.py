import sys
import base64
import json
import subprocess
import tempfile
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
    def test_generated_ed25519_signature_matches_verifier_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / "private.pem"
            pub = root / "public.pem"
            subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519",
                            "-out", str(key)], check=True, capture_output=True)
            subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout",
                            "-out", str(pub)], check=True, capture_output=True)
            reviewed = statement()
            attestation = sign(reviewed, key.read_text(encoding="ascii"))
            self.assertEqual(attestation["algorithm"], "ed25519-openssl-v1")
            signed_bytes = (b"AI-ORCHESTRATOR-LOCAL-REVIEW-v1\n" +
                            json.dumps(reviewed, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True).encode("ascii") + b"\n")
            message = root / "message.bin"
            signature = root / "signature.bin"
            message.write_bytes(signed_bytes)
            signature.write_bytes(base64.b64decode(attestation["signature_base64"]))
            command = ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey",
                       str(pub), "-rawin", "-in", str(message), "-sigfile", str(signature)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            message.write_bytes(signed_bytes + b"tampered")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

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
