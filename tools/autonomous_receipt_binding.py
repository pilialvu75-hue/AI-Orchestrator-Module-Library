"""Pure identity binding checks for a prospective protected verifier receipt.

This does not authenticate provenance or authorize a canonical transition.
"""
from __future__ import annotations

import re

_SHA = re.compile(r"[0-9a-f]{40}\\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\\Z")


def validate_receipt_binding(receipt: dict, expected: dict) -> dict:
    """Fail closed unless a receipt matches all exact immutable identities."""
    if not isinstance(receipt, dict) or not isinstance(expected, dict):
        raise ValueError("receipt and expected identity must be objects")
    fields = ("lane_id", "state_version", "claim_id", "packet_sha256",
              "repository", "pr_number", "head_sha")
    if set(receipt) != set(fields) or set(expected) != set(fields):
        raise ValueError("receipt identity fields must match the exact contract")
    for name in ("lane_id", "claim_id", "repository"):
        if not isinstance(expected[name], str) or not expected[name].strip():
            raise ValueError(f"invalid {name}")
    owner, repo = expected["repository"].split("/") if expected["repository"].count("/") == 1 else ("", "")
    if not owner or not repo or any(part != part.strip() or any(c.isspace() for c in part) for part in (owner, repo)):
        raise ValueError("invalid repository")
    for name in ("state_version", "pr_number"):
        value = expected[name]
        if type(value) is not int or value < (1 if name == "pr_number" else 0):
            raise ValueError(f"invalid {name}")
    for name, pattern in (("head_sha", _SHA), ("packet_sha256", _DIGEST)):
        if not isinstance(expected[name], str) or not pattern.fullmatch(expected[name]):
            raise ValueError(f"invalid {name}")
    if any(type(receipt[name]) is not type(expected[name]) or receipt[name] != expected[name] for name in fields):
        raise ValueError("receipt identity does not match canonical evidence")
    return dict(expected)
