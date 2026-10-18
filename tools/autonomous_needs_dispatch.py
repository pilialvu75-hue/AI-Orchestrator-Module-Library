"""Dispatch the protected needs-only verifier after a canonical lane handoff.

Called only from the serialized control-plane workflow after syncing main.
Never runs worker PR code and never applies lane mutations directly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tools.autonomous_canonical_identity import derive_canonical_receipt_identity
from tools.autonomous_ci_probe import fetch_json, probe as probe_ci
from tools.autonomous_independent_gates import LIBRARY_REPOSITORY
from tools.autonomous_needs_scope import verify_needs_only_scope
from tools.control_plane_manager import ROOT, _assert_claim_live, _validate_review_packet

LANE_FILE = ".airlab/control-plane/workstreams/library-curation.json"
WORKFLOW = "autonomous-ci-probe.yml"


def dispatch_ready_needs(*, root: Path = ROOT, token: str, changed_commit_only: bool = True,
                         now: datetime | None = None) -> bool:
    if not isinstance(token, str) or not token.strip():
        raise ValueError("GitHub token required to dispatch protected verification")
    if changed_commit_only:
        changed = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        if LANE_FILE not in changed:
            return False
    lane_path = root / LANE_FILE
    lane = json.loads(lane_path.read_text(encoding="utf-8"))
    if (lane.get("id") != "library-curation" or lane.get("role") != "worker"
            or lane.get("status") != "REVIEW_REQUIRED"):
        return False
    claim, packet = lane.get("active_claim"), lane.get("review_packet")
    if not isinstance(claim, dict) or not isinstance(packet, dict):
        return False
    if claim.get("repository") != LIBRARY_REPOSITORY or type(packet.get("pull_request")) is not int:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        _assert_claim_live(claim, now)
        _validate_review_packet("library-curation", claim, packet)
    except ValueError:
        return False
    pr_number = packet["pull_request"]
    try:
        pr = fetch_json(
            f"https://api.github.com/repos/{LIBRARY_REPOSITORY}/pulls/{pr_number}", token,
        )
        identity = derive_canonical_receipt_identity(lane, pr)
        verify_needs_only_scope(identity, token)
        ci = probe_ci(LIBRARY_REPOSITORY, pr_number, ["validate"], token)
        if (ci.get("head_sha") != identity["head_sha"]
                or ci.get("trusted_receipt") is not False
                or ci.get("completion_authorized") is not False):
            raise ValueError("unverified GitHub CI evidence")
    except (ValueError, KeyError):
        return False  # Unsafe/missing/stale evidence must not start an auto-approval.
    body = json.dumps({
        "ref": "main",
        "inputs": {
            "lane_id": "library-curation",
            "repository": LIBRARY_REPOSITORY,
            "pr_number": str(pr_number),
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{LIBRARY_REPOSITORY}/actions/workflows/{WORKFLOW}/dispatches",
        data=body, method="POST", headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "airlab-autonomous-needs-dispatch",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 204:
            raise ValueError("protected workflow dispatch was not accepted")
    return True


def main() -> int:
    try:
        dispatched = dispatch_ready_needs(token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"protected needs dispatch failed closed: {exc}", file=sys.stderr)
        return 1
    print("protected needs verifier dispatched" if dispatched else "no eligible new needs lane handoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
