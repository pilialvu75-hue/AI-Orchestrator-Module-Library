"""Queue a verified protected needs-only run for serialized inbox reconciliation.

The event-supplied run ID is only a lookup key. Every security-critical field
is fetched again from the GitHub API before writing a mutation request.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.autonomous_canonical_identity import derive_canonical_receipt_identity
from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_independent_gates import LIBRARY_REPOSITORY
from tools.autonomous_needs_scope import verify_needs_only_scope
from tools.autonomous_receipt_evidence_probe import probe_receipt_evidence
from tools.control_plane_manager import ROOT, _assert_claim_live, _validate_review_packet

LANE_FILE = ".airlab/control-plane/workstreams/library-curation.json"
WORKFLOW_PATH = ".github/workflows/autonomous-ci-probe.yml"


def enqueue_protected_needs_run(
    run_id: int, *, token: str, root: Path = ROOT,
    now: datetime | None = None,
) -> str | None:
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("invalid protected verifier run ID")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("protected GitHub token missing")
    lane = json.loads((root / LANE_FILE).read_text(encoding="utf-8"))
    if (lane.get("id") != "library-curation"
            or lane.get("status") != "REVIEW_REQUIRED"):
        return None
    claim, packet = lane.get("active_claim"), lane.get("review_packet")
    if not isinstance(claim, dict) or not isinstance(packet, dict):
        return None
    if claim.get("repository") != LIBRARY_REPOSITORY or type(packet.get("pull_request")) is not int:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        _assert_claim_live(claim, now)
        _validate_review_packet("library-curation", claim, packet)
    except ValueError:
        return None
    run = fetch_json(
        f"https://api.github.com/repos/{LIBRARY_REPOSITORY}/actions/runs/{run_id}", token,
    )
    if (not isinstance(run, dict) or type(run.get("run_attempt")) is not int
            or run["run_attempt"] <= 0
            or not isinstance(run.get("head_sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", run["head_sha"])):
        raise ValueError("protected verifier run metadata missing")
    repository = claim["repository"]
    pr = fetch_json(
        f"https://api.github.com/repos/{repository}/pulls/{packet['pull_request']}", token,
    )
    identity = derive_canonical_receipt_identity(lane, pr)
    verified = probe_receipt_evidence(
        receipt=identity, canonical_identity=identity,
        protected_repository=LIBRARY_REPOSITORY,
        run_id=run_id, run_attempt=run["run_attempt"],
        workflow_path=WORKFLOW_PATH,
        protected_sha=run["head_sha"], github_token=token,
    )
    scope = verify_needs_only_scope(identity, token)
    if (not isinstance(verified, dict)
            or verified.get("identity") != identity
            or verified.get("trusted_receipt") is not False
            or verified.get("completion_authorized") is not False
            or scope.get("scope_verified") is not True):
        raise ValueError("protected needs verifier did not authenticate exact scope")
    request_id = (
        f"autonomous-needs-{identity['claim_id']}-v{identity['state_version']}"
        f"-run{run_id}-a{run['run_attempt']}"
    )
    request = {
        "schema_version": 1, "request_id": request_id,
        "submitted_at": now.astimezone(timezone.utc).isoformat(),
        "actor_id": "system:github-actions:control-plane-reconcile",
        "lane_id": "library-curation",
        "operation": "autonomous_complete",
        "expected_state_version": identity["state_version"],
        "payload": {
            "protected_run_id": run_id, "run_attempt": run["run_attempt"],
            "protected_sha": run["head_sha"],
        },
    }
    inbox = root / ".airlab/control-plane/inbox"
    if any((inbox / state / f"{request_id}.json").exists()
           for state in ("pending", "processed", "quarantine")):
        return None
    destination = inbox / "pending" / f"{request_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(request, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return str(destination.relative_to(root))


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("usage: python -m tools.autonomous_needs_enqueue RUN_ID", file=sys.stderr)
        return 2
    try:
        path = enqueue_protected_needs_run(
            int(sys.argv[1]), token=os.environ.get("GITHUB_TOKEN", ""),
        )
        print(path if path else "no eligible protected needs completion")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"protected needs enqueue refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
