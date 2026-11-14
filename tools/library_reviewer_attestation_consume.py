"""Consume a source-bound reviewer attestation once in a protected local ledger.

The ledger is not shared across runners. This primitive cannot authorize a
certification; a production service must own durable replay state and policy.
"""
import hashlib
import hmac
import re
from library_reviewer_attestation_verify import verify_attestation
from library_reviewer_nonce_ledger import reserve_nonce


def verify_and_reserve(attestation, *, asset_id, source_sha256, evidence_sha256,
                       now, trusted_key_id, trusted_public_key_pem, trusted_key_sha256, ledger_dir):
    # The expected digest must originate in protected configuration, not in
    # the attestation or the candidate repository.
    if not isinstance(trusted_key_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', trusted_key_sha256):
        raise ValueError('trusted reviewer key pin is required')
    actual = hashlib.sha256(trusted_public_key_pem.encode('utf-8')).hexdigest()
    if not hmac.compare_digest(actual, trusted_key_sha256):
        return {'signature_verified': False, 'nonce_reserved': False,
                'certification_authorized': False}
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
