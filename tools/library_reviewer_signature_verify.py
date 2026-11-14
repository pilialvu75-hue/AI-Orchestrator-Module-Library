"""Verify detached RSA-SHA256 reviewer signatures against a trusted public key.

This helper does not authorize certification or publish packages. Trust keys must
be supplied by a separate protected workflow, never by untrusted candidate code.
"""
import base64
import binascii
import json
import subprocess
import tempfile
from pathlib import Path

SIGNED_FIELDS = ("schema", "asset_id", "source_sha256", "evidence_sha256",
                 "reviewer_key_id", "issued_at", "expires_at", "nonce")


def canonical_payload(attestation):
    return json.dumps({k: attestation[k] for k in SIGNED_FIELDS},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_signature(attestation, *, trusted_key_id, trusted_public_key_pem):
    if not isinstance(attestation, dict) or attestation.get("reviewer_key_id") != trusted_key_id:
        return False
    if not isinstance(trusted_key_id, str) or not trusted_key_id:
        return False
    if not isinstance(trusted_public_key_pem, str) or "BEGIN PUBLIC KEY" not in trusted_public_key_pem:
        return False
    try:
        signature = base64.b64decode(attestation["signature"], validate=True)
        if not signature or len(signature) > 8192:
            return False
        payload = canonical_payload(attestation)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "key.pem").write_text(trusted_public_key_pem, encoding="ascii")
            (directory / "payload.json").write_bytes(payload)
            (directory / "signature.bin").write_bytes(signature)
            result = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", str(directory / "key.pem"),
                 "-signature", str(directory / "signature.bin"), str(directory / "payload.json")],
                capture_output=True, timeout=10, check=False)
            return result.returncode == 0 and result.stdout.strip() == b"Verified OK"
    except (KeyError, TypeError, ValueError, UnicodeError, OSError, subprocess.TimeoutExpired,
            binascii.Error):
        return False
