"""Build a read-only receipt identity from canonical lane data and API-fetched PR head.

This is identity binding only; it does not authenticate evidence or authorize completion.
"""
from __future__ import annotations

import re
from tools.control_plane_manager import _review_packet_digest, _validate_review_packet

_SHA = re.compile(r"[0-9a-f]{40}\Z")


def derive_canonical_receipt_identity(lane: dict, pr: dict) -> dict:
    if not isinstance(lane, dict) or not isinstance(pr, dict):
        raise ValueError("canonical lane and API PR must be objects")
    if lane.get("role") != "worker" or lane.get("status") != "REVIEW_REQUIRED":
        raise ValueError("canonical lane is not awaiting worker review")
    claim = lane.get("active_claim")
    packet = lane.get("review_packet")
    if not isinstance(claim, dict) or not isinstance(packet, dict):
        raise ValueError("canonical claim and review packet are required")
    lane_id = lane.get("id")
    if not isinstance(lane_id, str) or not lane_id.strip():
        raise ValueError("invalid canonical lane ID")
    _validate_review_packet(lane_id, claim, packet)
    version = lane.get("state_version")
    if type(version) is not int or version < 0:
        raise ValueError("invalid canonical state version")
    number = packet.get("pull_request")
    if type(number) is not int or number <= 0 or pr.get("number") != number or type(pr.get("number")) is not int:
        raise ValueError("API PR number does not match canonical packet")
    repository = claim.get("repository")
    base_repo = (pr.get("base") or {}).get("repo") or {}
    if not isinstance(repository, str) or base_repo.get("full_name") != repository:
        raise ValueError("API PR repository does not match canonical claim")
    head = (pr.get("head") or {}).get("sha")
    if not isinstance(head, str) or not _SHA.fullmatch(head):
        raise ValueError("invalid API PR head SHA")
    head_repo = (pr.get("head") or {}).get("repo")
    if not isinstance(head_repo, dict) or head_repo.get("full_name") != repository:
        raise ValueError("PR head repository must match canonical repository")
    if pr.get("state") != "open":
        raise ValueError("PR must be open")
    return {"lane_id": lane_id, "state_version": version,
            "claim_id": claim["claim_id"], "packet_sha256": _review_packet_digest(packet),
            "repository": repository, "pr_number": number, "head_sha": head}
