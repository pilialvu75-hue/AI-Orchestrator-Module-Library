"""Build a read-only receipt identity from canonical lane data and API-fetched PR head.

This is identity binding only; it does not authenticate evidence or authorize completion.
"""
from __future__ import annotations

import re
from tools.control_plane_manager import _review_packet_digest, _validate_review_packet
from tools.autonomous_ci_probe import fetch_json

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
    base = pr.get("base")
    if not isinstance(base, dict) or not isinstance(base.get("repo"), dict):
        raise ValueError("invalid API PR base repository metadata")
    base_repo = base["repo"]
    if not isinstance(repository, str) or not repository.strip() or base_repo.get("full_name") != repository:
        raise ValueError("API PR repository does not match canonical claim")
    head_data = pr.get("head")
    if not isinstance(head_data, dict):
        raise ValueError("invalid API PR head metadata")
    head = head_data.get("sha")
    if not isinstance(head, str) or not _SHA.fullmatch(head):
        raise ValueError("invalid API PR head SHA")
    head_repo = head_data.get("repo")
    if not isinstance(head_repo, dict) or head_repo.get("full_name") != repository:
        raise ValueError("PR head repository must match canonical repository")
    if base.get("ref") != "main":
        raise ValueError("PR must target canonical main branch")
    if pr.get("draft") is True:
        raise ValueError("draft PR is not eligible for canonical completion")
    if pr.get("state") != "open":
        raise ValueError("PR must be open")
    return {"lane_id": lane_id, "state_version": version,
            "claim_id": claim["claim_id"], "packet_sha256": _review_packet_digest(packet),
            "repository": repository, "pr_number": number, "head_sha": head}


def fetch_canonical_pr_identity(lane: dict, github_token: str) -> dict:
    """Fetch the PR independently from GitHub, never from a worker-supplied PR body.

    The lane must be loaded from the protected canonical state by the caller.
    This function is read-only and cannot authorize completion.
    """
    if not isinstance(lane, dict):
        raise ValueError("canonical lane must be an object")
    claim = lane.get("active_claim")
    packet = lane.get("review_packet")
    if not isinstance(claim, dict) or not isinstance(packet, dict):
        raise ValueError("canonical claim and packet required")
    repository = claim.get("repository")
    number = packet.get("pull_request")
    if (not isinstance(repository, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or any(part in (".", "..") for part in repository.split("/"))
            or type(number) is not int or number <= 0):
        raise ValueError("invalid canonical GitHub PR locator")
    if not isinstance(github_token, str) or not github_token.strip():
        raise ValueError("GitHub token required")
    pr = fetch_json(f"https://api.github.com/repos/{repository}/pulls/{number}", github_token)
    return derive_canonical_receipt_identity(lane, pr)
