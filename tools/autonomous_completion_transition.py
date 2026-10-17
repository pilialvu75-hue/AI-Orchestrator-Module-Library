"""Pure autonomous completion transition, not exposed to untrusted inbox requests.

Only a future authenticated verifier may call this after rechecking the exact
canonical lane and protected receipt. Does not grant G6 reviewer approval.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from tools.autonomous_receipt_binding import validate_receipt_binding
from tools.autonomous_canonical_identity import derive_canonical_receipt_identity


def prepare_autonomous_transition(lane: dict, github_pr: dict,
                                  receipt: dict, verified_evidence: dict,
                                  *, now: datetime) -> dict:
    identity = derive_canonical_receipt_identity(lane, github_pr)
    validate_receipt_binding(receipt, identity)
    if (not isinstance(verified_evidence, dict)
            or verified_evidence.get("identity") != identity
            or verified_evidence.get("completion_authorized") is not True
            or verified_evidence.get("trusted_receipt") is not True):
        raise ValueError("authenticated autonomous completion authority required")
    # Current read-only evidence probe deliberately never returns authority.
    # No caller-controlled boolean may be promoted into a trusted receipt.
    raise ValueError("autonomous transition disabled pending independent receipt authentication")
