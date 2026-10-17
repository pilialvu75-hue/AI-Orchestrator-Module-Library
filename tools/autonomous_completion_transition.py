"""Pure autonomous completion transition, not exposed to untrusted inbox requests.

Only a future authenticated verifier may call this after rechecking the exact
canonical lane and protected receipt. Does not grant G6 reviewer approval.
"""
from __future__ import annotations

from datetime import datetime

from tools.autonomous_receipt_binding import validate_receipt_binding
from tools.control_plane_manager import _assert_claim_live, _review_gate_passed, _review_packet_digest
from tools.autonomous_canonical_identity import derive_canonical_receipt_identity


def prepare_autonomous_transition(lane: dict, github_pr: dict,
                                  receipt: dict, verified_evidence: dict,
                                  *, now: datetime) -> dict:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware verifier timestamp required")
    if not isinstance(lane, dict):
        raise ValueError("canonical lane must be an object")
    claim = lane.get("active_claim")
    if not isinstance(claim, dict):
        raise ValueError("canonical claim missing")
    _assert_claim_live(claim, now)
    gates = lane.get("gates")
    if not isinstance(gates, dict):
        raise ValueError("canonical gate evidence missing")
    required = ("G0_CLAIM", "G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION")
    missing = [gate for gate in required if not _review_gate_passed(gates.get(gate))]
    if missing:
        raise ValueError("autonomous completion gates unresolved: " + ", ".join(missing))
    runtime = gates.get("G5_TARGET_RUNTIME")
    if runtime not in ("NOT_APPLICABLE", "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE") and not _review_gate_passed(runtime):
        raise ValueError("target runtime G5 evidence unresolved")
    identity = derive_canonical_receipt_identity(lane, github_pr)
    attestation = lane.get("current_gate_attestation")
    if (not isinstance(attestation, dict)
            or attestation.get("claim_id") != claim.get("claim_id")
            or attestation.get("packet_sha256") != _review_packet_digest(lane["review_packet"])):
        raise ValueError("canonical gate attestation missing or stale")
    validate_receipt_binding(receipt, identity)
    if (not isinstance(verified_evidence, dict)
            or verified_evidence.get("identity") != identity
            or verified_evidence.get("completion_authorized") is not True
            or verified_evidence.get("trusted_receipt") is not True):
        raise ValueError("authenticated autonomous completion authority required")
    # Current read-only evidence probe deliberately never returns authority.
    # No caller-controlled boolean may be promoted into a trusted receipt.
    raise ValueError("autonomous transition disabled pending independent receipt authentication")
