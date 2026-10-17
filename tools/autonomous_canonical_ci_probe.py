"""Protected default-branch probe: bind verified GitHub CI to one canonical lane.

Run only from a pinned, protected main checkout. This is a read-only evidence
producer, never an authorization to complete a worker lane.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.autonomous_canonical_identity import derive_canonical_receipt_identity
from tools.autonomous_ci_probe import fetch_json, probe as probe_ci
from tools.control_plane_manager import ROOT, _assert_claim_live


def _load_object(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("canonical snapshot entry is not an object")
    return value


def probe_canonical_lane(
    lane_id: str, repository: str, pr_number: int, required_checks: list[str],
    github_token: str, *, root: Path = ROOT,
    now: datetime | None = None,
) -> dict:
    """Resolve identity ONLY from protected canonical files and GitHub's API."""
    if (not isinstance(lane_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", lane_id)
            or len(lane_id) > 128):
        raise ValueError("canonical lane ID is required")
    if not isinstance(root, Path):
        raise ValueError("canonical snapshot root must be a Path")
    canonical = _load_object(root / ".airlab/control-plane/canonical-state.json")
    if canonical.get("schema_version") != 1:
        raise ValueError("invalid canonical snapshot schema")
    if ((canonical.get("authority") or {}).get("repository")
            != "pilialvu75-hue/AI-Orchestrator-Module-Library"):
        raise ValueError("untrusted canonical snapshot authority")
    paths = canonical.get("workstreams")
    if not isinstance(paths, list) or not paths:
        raise ValueError("canonical workstream registry is unavailable")
    lanes = []
    base_dir = (root / ".airlab/control-plane/workstreams").resolve()
    for rel in paths:
        if not isinstance(rel, str) or not rel.startswith(".airlab/control-plane/workstreams/"):
            raise ValueError("invalid canonical workstream path")
        path = (root / rel).resolve()
        if not path.is_relative_to(base_dir) or path.suffix != ".json" or path.is_symlink():
            raise ValueError("canonical workstream path escapes protected directory")
        lane = _load_object(path)
        if lane.get("id") == lane_id:
            lanes.append(lane)
    if len(lanes) != 1:
        raise ValueError("canonical lane must exist exactly once")
    lane = lanes[0]
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware verifier timestamp required")
    claim = lane.get("active_claim")
    if not isinstance(claim, dict):
        raise ValueError("canonical claim is missing")
    _assert_claim_live(claim, now)

    # Query the PR independently. The worker cannot supply a replacement PR
    # response, packet digest, or state_version.
    if (not isinstance(repository, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or any(part in (".", "..") for part in repository.split("/"))
            or type(pr_number) is not int or pr_number <= 0):
        raise ValueError("invalid PR repository or number")
    if not isinstance(github_token, str) or not github_token.strip():
        raise ValueError("GitHub token is required")
    pr = fetch_json(
        f"https://api.github.com/repos/{repository}/pulls/{pr_number}", github_token,
    )
    identity = derive_canonical_receipt_identity(lane, pr)
    if identity["repository"] != repository or identity["pr_number"] != pr_number:
        raise ValueError("canonical claim does not match requested PR")
    ci = probe_ci(repository, pr_number, required_checks, github_token)
    if (not isinstance(ci, dict) or ci.get("repository") != repository
            or ci.get("pr_number") != pr_number
            or ci.get("head_sha") != identity["head_sha"]
            or ci.get("trusted_receipt") is not False
            or ci.get("completion_authorized") is not False):
        raise ValueError("canonical lane identity differs from live GitHub CI")
    # Re-read the protected lane after network calls. A changed local snapshot
    # cannot silently reuse evidence collected for an earlier claim/version.
    refreshed = _load_object(next(path for path in ((root / rel).resolve() for rel in paths)
                                 if _load_object(path).get("id") == lane_id))
    if refreshed != lane:
        raise ValueError("canonical lane changed during CI verification")
    return {**ci, "canonical_identity": identity}


def main() -> int:
    if len(sys.argv) < 5:
        print("usage: python -m tools.autonomous_canonical_ci_probe LANE REPO PR CHECK...", file=sys.stderr)
        return 2
    try:
        result = probe_canonical_lane(
            sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4:],
            os.environ.get("GITHUB_TOKEN", ""),
        )
    except (ValueError, OSError, KeyError) as exc:
        print(f"canonical CI probe refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
