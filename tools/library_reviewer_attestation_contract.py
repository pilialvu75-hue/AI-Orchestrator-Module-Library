"""Validate source-bound reviewer attestation metadata before cryptographic verification.

This is a structural gate, NOT a signature verifier or authorization.
"""
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = ("schema", "asset_id", "source_sha256", "evidence_sha256",
            "reviewer_key_id", "issued_at", "expires_at", "nonce", "signature")


def validate_contract(attestation, *, asset_id, source_sha256, evidence_sha256, now):
    if not isinstance(attestation, dict) or set(attestation) != set(REQUIRED):
        raise ValueError("invalid attestation fields")
    if attestation["schema"] != "aivexus.library.reviewer-attestation.v1":
        raise ValueError("invalid attestation schema")
    if not isinstance(asset_id, str) or not asset_id or attestation["asset_id"] != asset_id:
        raise ValueError("asset identity mismatch")
    for field, expected in (("source_sha256", source_sha256),
                            ("evidence_sha256", evidence_sha256)):
        value = attestation[field]
        if not isinstance(value, str) or not HEX64.fullmatch(value) or value != expected:
            raise ValueError(field + " mismatch")
    for field in ("reviewer_key_id", "nonce", "signature"):
        value = attestation[field]
        if not isinstance(value, str) or not value or len(value) > 1024:
            raise ValueError("invalid " + field)
    issued, expires = attestation["issued_at"], attestation["expires_at"]
    if (type(issued) is not int or type(expires) is not int
            or type(now) is not int or not issued <= now < expires
            or expires - issued > 86400):
        raise ValueError("expired or invalid attestation validity")
    # Successful structural validation is never cryptographic approval.
    return {"contract_valid": True, "signature_verified": False,
            "certification_authorized": False}
