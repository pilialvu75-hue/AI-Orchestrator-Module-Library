"""Strict, read-only autonomous fast path for the Library needs queue.

Only a *single* changed non-executable metadata file is eligible. The PR's
exact SHA must already have passed the independent protected CI audit.
This is not a generic software/module-certification review.
"""
from __future__ import annotations

import re

from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_independent_gates import LIBRARY_REPOSITORY

_SAFE_FILE = "catalog/needs.json"
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def verify_needs_only_scope(identity: dict, github_token: str) -> dict:
    if (not isinstance(identity, dict)
            or identity.get("lane_id") != "library-curation"
            or identity.get("repository") != LIBRARY_REPOSITORY
            or type(identity.get("pr_number")) is not int
            or identity["pr_number"] <= 0
            or not isinstance(identity.get("head_sha"), str)
            or not _SHA.fullmatch(identity["head_sha"])):
        raise ValueError("autonomous needs policy supports only an exact Library PR")
    if not isinstance(github_token, str) or not github_token.strip():
        raise ValueError("GitHub token required to verify autonomous change scope")
    base = f"https://api.github.com/repos/{LIBRARY_REPOSITORY}"
    pr_number, sha = identity["pr_number"], identity["head_sha"]
    pr = fetch_json(f"{base}/pulls/{pr_number}", github_token)
    if (not isinstance(pr, dict)
            or type(pr.get("number")) is not int or pr["number"] != pr_number
            or pr.get("state") != "open" or pr.get("draft") is not False
            or (pr.get("head") or {}).get("sha") != sha
            or ((pr.get("head") or {}).get("repo") or {}).get("full_name") != LIBRARY_REPOSITORY
            or (pr.get("base") or {}).get("ref") != "main"
            or ((pr.get("base") or {}).get("repo") or {}).get("full_name") != LIBRARY_REPOSITORY):
        raise ValueError("autonomous needs PR identity changed or is not eligible")

    # GitHub's PR file endpoint is a list, not a counted response. Require
    # exactly one entry so pagination can never hide additional changes.
    files = fetch_json(f"{base}/pulls/{pr_number}/files?per_page=100", github_token)
    if not isinstance(files, list) or len(files) != 1:
        raise ValueError("autonomous needs change must modify exactly one file")
    entry = files[0]
    if (not isinstance(entry, dict)
            or entry.get("filename") != _SAFE_FILE
            or entry.get("status") != "modified"
            or "previous_filename" in entry
            or type(entry.get("changes")) is not int
            or entry["changes"] <= 0
            or not isinstance(entry.get("sha"), str)
            or not _SHA.fullmatch(entry["sha"])):
        raise ValueError("autonomous needs change includes unapproved file or status")

    content = fetch_json(f"{base}/contents/{_SAFE_FILE}?ref={sha}", github_token)
    if (not isinstance(content, dict)
            or content.get("type") != "file"
            or content.get("path") != _SAFE_FILE
            or content.get("sha") != entry["sha"]):
        raise ValueError("autonomous needs file identity differs from PR head")

    # Re-read PR once after the file/blob evidence, to reject a moving head.
    latest = fetch_json(f"{base}/pulls/{pr_number}", github_token)
    if (not isinstance(latest, dict)
            or (latest.get("head") or {}).get("sha") != sha
            or latest.get("state") != "open"
            or latest.get("draft") is not False):
        raise ValueError("autonomous needs PR head changed during verification")
    return {
        "profile": "library-needs-only-v1",
        "canonical_identity": identity,
        "changed_file": _SAFE_FILE,
        "file_blob_sha": entry["sha"],
        "scope_verified": True,
        "runtime_applicable": False,
        "executable_changes": False,
    }
