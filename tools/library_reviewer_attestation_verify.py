"""Combined reviewer attestation validation: structure + pinned-key signature.

This verification is a prerequisite only. It does not issue certification.
Nonce replay protection and authorization policy belong to a protected,
stateful reviewer service and MUST NOT be inferred from this result.
"""
from library_reviewer_attestation_contract import validate_contract
from library_reviewer_signature_verify import verify_signature


def verify_attestation(attestation, *, asset_id, source_sha256, evidence_sha256,
                       now, trusted_key_id, trusted_public_key_pem):
    metadata = validate_contract(
        attestation, asset_id=asset_id, source_sha256=source_sha256,
        evidence_sha256=evidence_sha256, now=now)
    signature_ok = verify_signature(
        attestation, trusted_key_id=trusted_key_id,
        trusted_public_key_pem=trusted_public_key_pem)
    return {"contract_valid": metadata["contract_valid"],
            "signature_verified": signature_ok,
            "certification_authorized": False}
