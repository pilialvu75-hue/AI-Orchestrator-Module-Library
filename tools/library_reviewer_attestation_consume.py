"""Consume a source-bound reviewer attestation once in a protected local ledger.

The ledger is not shared across runners. This primitive cannot authorize a
certification; a production service must own durable replay state and policy.
"""
from library_reviewer_attestation_verify import verify_attestation
from library_reviewer_nonce_ledger import reserve_nonce


def verify_and_reserve(attestation, *, asset_id, source_sha256, evidence_sha256,
                       now, trusted_key_id, trusted_public_key_pem, ledger_dir):
    verified = verify_attestation(
        attestation, asset_id=asset_id, source_sha256=source_sha256,
        evidence_sha256=evidence_sha256, now=now, trusted_key_id=trusted_key_id,
        trusted_public_key_pem=trusted_public_key_pem)
    if not verified["signature_verified"]:
        return {"signature_verified": False, "nonce_reserved": False,
                "certification_authorized": False}
    reserved = reserve_nonce(reviewer_key_id=trusted_key_id,
                             nonce=attestation["nonce"], ledger_dir=ledger_dir)
    return {"signature_verified": True, "nonce_reserved": reserved,
            "certification_authorized": False}
