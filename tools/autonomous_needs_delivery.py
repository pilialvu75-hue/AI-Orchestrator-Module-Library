"""Protected exact-head merge and durable finalize request for Library needs only.

This module is executed solely by the serialized default-branch reconciler.
It never trusts a worker-provided merge flag: the canonical prepared identity
and GitHub PR/commit/blob are independently verified at each stage.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_canonical_identity import derive_canonical_receipt_identity
from tools.autonomous_independent_gates import LIBRARY_REPOSITORY
from tools.autonomous_needs_scope import verify_needs_only_scope
from tools.autonomous_receipt_evidence_probe import probe_receipt_evidence
from tools.control_plane_manager import ROOT, _assert_claim_live, _review_packet_digest

LANE_REL = Path(".airlab/control-plane/workstreams/library-curation.json")
INBOX_REL = Path(".airlab/control-plane/inbox")
WORKFLOW = ".github/workflows/autonomous-ci-probe.yml"
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _pending(root: Path) -> tuple[dict, dict, dict, dict] | None:
    path = root / LANE_REL
    if not path.is_file():
        return None
    lane = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(lane, dict) or lane.get("id") != "library-curation"
            or lane.get("role") != "worker"
            or lane.get("status") != "REVIEW_REQUIRED"):
        return None
    claim, packet, pending = (
        lane.get("active_claim"), lane.get("review_packet"),
        lane.get("pending_needs_delivery"),
    )
    if not all(isinstance(v, dict) for v in (claim, packet, pending)):
        return None
    identity = pending.get("identity")
    if (not isinstance(identity, dict)
            or pending.get("profile") != "library-needs-only-v1"
            or pending.get("changed_file") != "catalog/needs.json"
            or identity.get("lane_id") != "library-curation"
            or identity.get("repository") != LIBRARY_REPOSITORY
            or claim.get("repository") != LIBRARY_REPOSITORY
            or identity.get("claim_id") != claim.get("claim_id")
            or identity.get("packet_sha256") != _review_packet_digest(packet)
            or identity.get("pr_number") != packet.get("pull_request")
            or type(identity.get("state_version")) is not int
            or lane.get("state_version") != identity["state_version"] + 1
            or not isinstance(identity.get("head_sha"), str)
            or not _SHA.fullmatch(identity["head_sha"])
            or not isinstance(pending.get("scope_blob_sha"), str)
            or not _SHA.fullmatch(pending["scope_blob_sha"])
            or type(pending.get("protected_run_id")) is not int
            or type(pending.get("protected_run_attempt")) is not int
            or not isinstance(pending.get("protected_sha"), str)
            or not _SHA.fullmatch(pending["protected_sha"])
            or (lane.get("gates") or {}).get("G0_CLAIM") != "PASS"
            or any((lane.get("gates") or {}).get(gate) != "PASS"
                   for gate in ("G1_IMPLEMENTATION", "G2_STATIC",
                                "G3_CI", "G4_INTEGRATION"))
            or (lane.get("gates") or {}).get("G7_CANONICAL_SYNC") != "PENDING"
            or (packet.get("roadmap_impact") or {}).get("material") is not False
            or (lane.get("gates") or {}).get("G6_REVIEWER") != "PENDING"
            or (lane.get("reviewer") or {}).get("state") != "PENDING"
            or (lane.get("gates") or {}).get("G5_TARGET_RUNTIME") not in
                ("NOT_APPLICABLE", "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE")):
        raise ValueError("prepared needs delivery does not match canonical claim and safety gates")
    return lane, claim, packet, pending


def verify_merged_delivery(pending: dict, token: str) -> dict:
    """Independent read-only proof that the exact attested needs blob is in main."""
    if not isinstance(token, str) or not token.strip():
        raise ValueError("GitHub token required to verify merged delivery")
    identity = pending.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("prepared canonical merge identity missing")
    repo = identity.get("repository")
    number = identity.get("pr_number")
    sha = identity.get("head_sha")
    blob = pending.get("scope_blob_sha")
    if (repo != LIBRARY_REPOSITORY or type(number) is not int or number <= 0
            or not isinstance(sha, str) or not _SHA.fullmatch(sha)
            or not isinstance(blob, str) or not _SHA.fullmatch(blob)):
        raise ValueError("unsupported merged needs identity")
    base = f"https://api.github.com/repos/{repo}"
    pr = fetch_json(f"{base}/pulls/{number}", token)
    merge_sha = pr.get("merge_commit_sha") if isinstance(pr, dict) else None
    if (not isinstance(pr, dict) or pr.get("number") != number
            or pr.get("state") != "closed"
            or pr.get("merged") is not True
            or pr.get("draft") is not False
            or (pr.get("head") or {}).get("sha") != sha
            or (pr.get("base") or {}).get("ref") != "main"
            or ((pr.get("base") or {}).get("repo") or {}).get("full_name") != repo
            or not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha)):
        raise ValueError("GitHub does not confirm merge of the exact attested PR head")
    # The merge commit must be part of main, even when main has advanced.
    comparison = fetch_json(f"{base}/compare/{merge_sha}...main", token)
    if (not isinstance(comparison, dict)
            or comparison.get("status") not in ("ahead", "identical")
            or type(comparison.get("behind_by")) is not int
            or comparison["behind_by"] != 0
            or (comparison.get("base_commit") or {}).get("sha") != merge_sha):
        raise ValueError("merge commit is not an ancestor of the current main branch")
    current = fetch_json(f"{base}/contents/catalog/needs.json?ref=main", token)
    if (not isinstance(current, dict)
            or current.get("path") != "catalog/needs.json"
            or current.get("type") != "file"
            or current.get("sha") != blob):
        raise ValueError("verified needs blob has not been delivered to main")
    return {
        "pr_number": number,
        "head_sha": sha,
        "merge_commit_sha": merge_sha,
        "file_blob_sha": blob,
    }


def merge_prepared_needs(*, token: str, root: Path = ROOT,
                         now: datetime | None = None) -> bool:
    found = _pending(root)
    if found is None:
        return False
    _lane, claim, _packet, pending = found
    if not isinstance(token, str) or not token.strip():
        raise ValueError("protected GitHub merge token missing")
    now = now or datetime.now(timezone.utc)
    identity = pending["identity"]
    number, repo = identity["pr_number"], identity["repository"]
    base = f"https://api.github.com/repos/{repo}"
    pr = fetch_json(f"{base}/pulls/{number}", token)
    if pr.get("merged") is True:
        verify_merged_delivery(pending, token)
        return True
    _assert_claim_live(claim, now)
    if (pr.get("state") != "open" or pr.get("draft") is not False
            or (pr.get("head") or {}).get("sha") != identity["head_sha"]):
        raise ValueError("prepared needs PR changed before protected merge")
    # Scope/CI are checked again immediately before the external merge. A
    # stale receipt cannot authorize a newly edited worker branch.
    scope = verify_needs_only_scope(identity, token)
    if scope.get("file_blob_sha") != pending["scope_blob_sha"]:
        raise ValueError("needs blob changed after protected verification")
    verified = probe_receipt_evidence(
        receipt=identity, canonical_identity=identity,
        protected_repository=repo,
        run_id=pending["protected_run_id"],
        run_attempt=pending["protected_run_attempt"],
        workflow_path=WORKFLOW,
        protected_sha=pending["protected_sha"],
        github_token=token,
    )
    if (verified.get("identity") != identity
            or verified.get("trusted_receipt") is not False
            or verified.get("completion_authorized") is not False):
        raise ValueError("protected needs receipt changed before merge")
    request = urllib.request.Request(
        f"{base}/pulls/{number}/merge",
        data=json.dumps({
            "sha": identity["head_sha"], "merge_method": "merge",
            "commit_title": "Merge independently verified Library needs-only PR",
        }).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "airlab-protected-needs-delivery",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            merge = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"GitHub rejected protected needs merge HTTP {exc.code}") from exc
    if not isinstance(merge, dict) or merge.get("merged") is not True:
        raise ValueError("GitHub did not confirm exact-head needs merge")
    confirmed = verify_merged_delivery(pending, token)
    if merge.get("sha") != confirmed["merge_commit_sha"]:
        raise ValueError("merge response differs from independently fetched merge commit")
    return True


def enqueue_verified_delivery(*, token: str, root: Path = ROOT,
                              now: datetime | None = None) -> str | None:
    found = _pending(root)
    if found is None:
        return None
    lane, _claim, _packet, pending = found
    confirmed = verify_merged_delivery(pending, token)
    identity = pending["identity"]
    request_id = (
        f"needs-delivered-{identity['claim_id']}-v{lane['state_version']}"
        f"-pr{identity['pr_number']}"
    )
    request = {
        "schema_version": 1,
        "request_id": request_id,
        "submitted_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "actor_id": "system:github-actions:control-plane-reconcile",
        "lane_id": "library-curation",
        "operation": "autonomous_finalize_needs",
        "expected_state_version": lane["state_version"],
        "payload": confirmed,
    }
    inbox = root / INBOX_REL
    if any((inbox / state / f"{request_id}.json").exists()
           for state in ("pending", "processed", "quarantine")):
        return None
    target = inbox / "pending" / f"{request_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(target.relative_to(root))


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"merge", "enqueue"}:
        print("usage: python -m tools.autonomous_needs_delivery merge|enqueue", file=sys.stderr)
        return 2
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        if sys.argv[1] == "merge":
            value = merge_prepared_needs(token=token)
            print("needs merge verified" if value else "no pending needs delivery")
        else:
            path = enqueue_verified_delivery(token=token)
            print(path if path else "no merged needs to finalize")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"protected needs delivery refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
