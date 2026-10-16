"""Pure, fail-closed GitHub CI evidence verifier.

This module validates GitHub API response objects supplied by a protected runner.
It does not grant approval or write canonical state.
"""
from __future__ import annotations

import re
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}\Z")


def verify_pr_checks(
    *,
    pr: dict[str, Any],
    checks: list[dict[str, Any]],
    repository: str,
    expected_head_sha: str,
    required_check_names: list[str],
) -> dict[str, Any]:
    """Validate exact-commit check evidence; return a non-authoritative report."""
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise ValueError("repository must be owner/name")
    if not isinstance(expected_head_sha, str) or not _SHA.fullmatch(expected_head_sha):
        raise ValueError("expected head SHA must be 40 lowercase hex characters")
    if not isinstance(pr, dict) or pr.get("state") != "open":
        raise ValueError("PR must be open")
    if (pr.get("head") or {}).get("sha") != expected_head_sha:
        raise ValueError("PR head changed")
    head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    if head_repo != repository:
        raise ValueError("PR head repository mismatch")
    if not isinstance(required_check_names, list) or not required_check_names:
        raise ValueError("required checks must be nonempty")
    if any(not isinstance(name, str) or not name.strip() for name in required_check_names):
        raise ValueError("invalid required check name")
    if len(set(required_check_names)) != len(required_check_names):
        raise ValueError("duplicate required check name")
    if not isinstance(checks, list) or any(not isinstance(item, dict) for item in checks):
        raise ValueError("checks must be a list of objects")
    verified = {}
    for name in required_check_names:
        matches = [check for check in checks if check.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"check {name!r} missing or ambiguous")
        check = matches[0]
        if check.get("head_sha") != expected_head_sha:
            raise ValueError(f"check {name!r} head mismatch")
        if check.get("status") != "completed" or check.get("conclusion") != "success":
            raise ValueError(f"check {name!r} not successful")
        app = check.get("app") or {}
        if app.get("slug") != "github-actions":
            raise ValueError(f"check {name!r} has untrusted producer")
        verified[name] = check.get("id")
    return {"repository": repository, "head_sha": expected_head_sha, "verified_checks": verified,
            "trusted_receipt": False, "completion_authorized": False}
