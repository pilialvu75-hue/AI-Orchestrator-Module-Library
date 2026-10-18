"""Bounded replay-safe catch-up for protected Library needs CI receipts.

GitHub's automatic workflow_run delivery is not guaranteed when the upstream
workflow was dispatched using the repository GITHUB_TOKEN. The already hourly
serialized reconciler must be able to discover the completed protected run
without trusting an event or re-issuing any worker approval.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_independent_gates import LIBRARY_REPOSITORY
from tools.autonomous_needs_enqueue import enqueue_protected_needs_run
from tools.control_plane_manager import ROOT, _assert_claim_live, _validate_review_packet

LANE_REL = Path(".airlab/control-plane/workstreams/library-curation.json")
WORKFLOW_PATH = ".github/workflows/autonomous-ci-probe.yml"
WORKFLOW_FILE = "autonomous-ci-probe.yml"
MAX_CANDIDATES = 20
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("protected workflow timestamp missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid protected workflow timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("protected workflow timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def reconcile_verified_needs(
    *, root: Path = ROOT, token: str, now: datetime | None = None,
) -> str | None:
    """Queue one independently authenticated receipt; never approve work itself.

    Returns an inbox request path when one is queued. An ineligible lane is a
    no-op. Candidate workflow run ids are only hints: the existing enqueue
    path independently fetches the run, exact artifact, PR, CI and safe scope.
    """
    lane_path = root / LANE_REL
    if not lane_path.is_file():
        return None
    lane = json.loads(lane_path.read_text(encoding="utf-8"))
    if (not isinstance(lane, dict)
            or lane.get("id") != "library-curation"
            or lane.get("role") != "worker"
            or lane.get("status") != "REVIEW_REQUIRED"):
        return None
    claim, packet = lane.get("active_claim"), lane.get("review_packet")
    if not isinstance(claim, dict) or not isinstance(packet, dict):
        return None
    if (claim.get("repository") != LIBRARY_REPOSITORY
            or type(packet.get("pull_request")) is not int
            or packet["pull_request"] <= 0):
        return None
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware receipt scan timestamp required")
    try:
        _assert_claim_live(claim, now)
        _validate_review_packet("library-curation", claim, packet)
    except ValueError:
        return None
    if not isinstance(token, str) or not token.strip():
        raise ValueError("protected GitHub token missing for receipt reconciliation")
    url = (
        f"https://api.github.com/repos/{LIBRARY_REPOSITORY}/actions/"
        f"workflows/{WORKFLOW_FILE}/runs?event=workflow_dispatch&branch=main&per_page=100"
    )
    listing = fetch_json(url, token)
    if not isinstance(listing, dict):
        raise ValueError("protected workflow run listing must be an object")
    total = listing.get("total_count")
    runs = listing.get("workflow_runs")
    if (type(total) is not int or total < 0
            or not isinstance(runs, list)
            or len(runs) > 100 or len(runs) > total):
        raise ValueError("invalid or incomplete protected workflow run listing")
    started_at = _parse_utc(claim.get("started_at"))
    candidates = []
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("protected workflow run listing contains invalid entry")
        created = _parse_utc(run.get("created_at"))
        if created < started_at or created > now:
            continue
        if (run.get("event") != "workflow_dispatch"
                or run.get("path") != WORKFLOW_PATH
                or run.get("head_branch") != "main"
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or (run.get("repository") or {}).get("full_name") != LIBRARY_REPOSITORY
                or type(run.get("id")) is not int or run["id"] <= 0
                or type(run.get("run_attempt")) is not int or run["run_attempt"] <= 0
                or not isinstance(run.get("head_sha"), str)
                or not _SHA.fullmatch(run["head_sha"])):
            continue
        candidates.append((created, run["id"]))
    candidates.sort(reverse=True)
    for _, run_id in candidates[:MAX_CANDIDATES]:
        try:
            path = enqueue_protected_needs_run(
                run_id, token=token, root=root, now=now,
            )
        except (ValueError, OSError, KeyError) as error:
            # A stale or malicious candidate must not stop later valid runs;
            # log a refusal, never grant authority or change the worker lane.
            print(f"protected needs run {run_id} refused: {error}", file=sys.stderr)
            continue
        if path is not None:
            return path
    return None


def main() -> int:
    try:
        result = reconcile_verified_needs(token=os.environ.get("GITHUB_TOKEN", ""))
    except (ValueError, OSError, KeyError) as exc:
        print(f"protected needs reconciliation failed closed: {exc}", file=sys.stderr)
        return 1
    print(result if result else "no eligible completed protected needs receipt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
