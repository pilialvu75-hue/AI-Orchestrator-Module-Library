#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / ".airlab/control-plane/external-change-registry.json"
WORKSTREAM_DIR = ROOT / ".airlab/control-plane/workstreams"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _api_get(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-orchestrator-external-change-ingress/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {error.code} for {url}: {body[:500]}") from error


def _repo_api(repository: str, suffix: str, token: str | None) -> Any:
    owner, name = repository.split("/", 1)
    return _api_get(
        f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}/{suffix}",
        token,
    )


def _closed_pr_changes(repository: str, cursor: str, token: str | None) -> list[dict[str, Any]]:
    pulls = _repo_api(repository, "pulls?state=closed&sort=updated&direction=asc&per_page=100", token)
    changes: list[dict[str, Any]] = []
    for pull in pulls:
        merged_at = pull.get("merged_at")
        if not merged_at or merged_at <= cursor:
            continue
        changes.append({
            "kind": "pull_request",
            "repository": repository,
            "pull_request": int(pull["number"]),
            "merged_at": merged_at,
            "merge_sha": pull.get("merge_commit_sha"),
            "head_branch": (pull.get("head") or {}).get("ref"),
            "base_branch": (pull.get("base") or {}).get("ref"),
            "title": pull.get("title") or "",
            "html_url": pull.get("html_url"),
        })
    return changes


def _direct_commit_changes(
    repository: str,
    cursor: str,
    known_pr_merge_shas: set[str],
    token: str | None,
) -> list[dict[str, Any]]:
    repo = _repo_api(repository, "", token)
    default_branch = repo.get("default_branch") or "main"
    encoded_since = urllib.parse.quote(cursor)
    commits = _repo_api(
        repository,
        f"commits?sha={urllib.parse.quote(default_branch)}&since={encoded_since}&per_page=100",
        token,
    )
    changes: list[dict[str, Any]] = []
    for item in commits:
        sha = item.get("sha")
        if not sha or sha in known_pr_merge_shas:
            continue
        commit = item.get("commit") or {}
        committer = commit.get("committer") or {}
        committed_at = committer.get("date")
        if not committed_at or committed_at <= cursor:
            continue
        parents = item.get("parents") or []
        # A merge commit should normally have been represented by a merged PR. Keep an
        # unmatched merge visible rather than silently classifying it as a direct push.
        kind = "unmatched_merge_commit" if len(parents) > 1 else "direct_commit"
        changes.append({
            "kind": kind,
            "repository": repository,
            "commit_sha": sha,
            "committed_at": committed_at,
            "base_branch": default_branch,
            "message": (commit.get("message") or "").splitlines()[0],
            "html_url": item.get("html_url"),
        })
    return changes


def fetch_changes(registry: dict[str, Any], token: str | None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in registry.get("tracked_repositories") or []:
        repository = entry["repository"]
        cursor = entry["cursor_merged_at"]
        pulls = _closed_pr_changes(repository, cursor, token)
        changes = list(pulls)
        if entry.get("detect_direct_commits", repository != "pilialvu75-hue/AI-Orchestrator-Module-Library"):
            merge_shas = {str(change.get("merge_sha")) for change in pulls if change.get("merge_sha")}
            changes.extend(_direct_commit_changes(repository, cursor, merge_shas, token))
        result[repository] = sorted(
            changes,
            key=lambda item: str(item.get("merged_at") or item.get("committed_at") or ""),
        )
    return result


def _workstreams(root: Path) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for path in sorted((root / ".airlab/control-plane/workstreams").glob("*.json")):
        try:
            value = _load(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            lanes.append(value)
    return lanes


def _flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _flatten_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten_strings(child)


def _canonical_evidence_matches(change: dict[str, Any], lanes: list[dict[str, Any]]) -> tuple[bool, str | None]:
    repository = str(change["repository"])
    repo_name = repository.split("/", 1)[1]
    pr_number = change.get("pull_request")
    merge_sha = change.get("merge_sha") or change.get("commit_sha")
    needles: list[re.Pattern[str]] = []
    if pr_number is not None:
        number = re.escape(str(pr_number))
        needles.extend([
            re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(repository)}#{number}(?!\d)", re.IGNORECASE),
            re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(repo_name)}#{number}(?!\d)", re.IGNORECASE),
        ])
    for lane in lanes:
        lane_id = str(lane.get("id") or "unknown")
        claim = lane.get("active_claim")
        if isinstance(claim, dict) and claim.get("repository") == repository:
            branch = change.get("head_branch")
            if branch and claim.get("branch") == branch:
                return True, f"active_claim:{lane_id}:{claim.get('claim_id')}"
        for text in _flatten_strings(lane):
            if merge_sha and len(str(merge_sha)) >= 7 and str(merge_sha) in text:
                return True, f"canonical_evidence:{lane_id}:merge_sha"
            if any(pattern.search(text) for pattern in needles):
                return True, f"canonical_evidence:{lane_id}:pull_request"
    return False, None


def _incident_id(change: dict[str, Any]) -> str:
    stable = "|".join([
        str(change.get("repository") or ""),
        str(change.get("kind") or ""),
        str(change.get("pull_request") or ""),
        str(change.get("merge_sha") or change.get("commit_sha") or ""),
    ])
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def scan_registry(
    registry: dict[str, Any],
    lanes: list[dict[str, Any]],
    changes_by_repo: dict[str, list[dict[str, Any]]],
    *,
    now: str,
) -> dict[str, Any]:
    incidents = registry.setdefault("incidents", [])
    existing = {str(item.get("incident_id")): item for item in incidents if isinstance(item, dict)}
    for repo_entry in registry.get("tracked_repositories") or []:
        repository = repo_entry["repository"]
        cursor = str(repo_entry["cursor_merged_at"])
        newest = cursor
        for change in changes_by_repo.get(repository, []):
            observed_at = str(change.get("merged_at") or change.get("committed_at") or cursor)
            if observed_at <= cursor:
                continue
            newest = max(newest, observed_at)
            matched, match_ref = _canonical_evidence_matches(change, lanes)
            if matched:
                continue
            incident_id = _incident_id(change)
            if incident_id in existing:
                continue
            incident = {
                "incident_id": incident_id,
                "status": "UNRECONCILED",
                "detected_at": now,
                "repository": repository,
                "kind": change.get("kind"),
                "pull_request": change.get("pull_request"),
                "merge_sha": change.get("merge_sha"),
                "commit_sha": change.get("commit_sha"),
                "head_branch": change.get("head_branch"),
                "base_branch": change.get("base_branch"),
                "change_at": observed_at,
                "title": change.get("title") or change.get("message") or "",
                "url": change.get("html_url"),
                "match_ref": match_ref,
                "reconciliation": null,
            }
            incidents.append(incident)
            existing[incident_id] = incident
        repo_entry["cursor_merged_at"] = newest
    registry["last_scan_at"] = now
    return registry


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append("external-change registry schema_version must be 1")
    repositories: set[str] = set()
    for index, entry in enumerate(registry.get("tracked_repositories") or []):
        if not isinstance(entry, dict):
            errors.append(f"tracked_repositories[{index}] must be an object")
            continue
        repository = entry.get("repository")
        if not isinstance(repository, str) or "/" not in repository:
            errors.append(f"tracked_repositories[{index}].repository is invalid")
        elif repository in repositories:
            errors.append(f"duplicate tracked repository: {repository}")
        else:
            repositories.add(repository)
        if not entry.get("baseline_at") or not entry.get("cursor_merged_at"):
            errors.append(f"tracked_repositories[{index}] requires baseline_at and cursor_merged_at")
    incident_ids: set[str] = set()
    for index, incident in enumerate(registry.get("incidents") or []):
        if not isinstance(incident, dict):
            errors.append(f"incidents[{index}] must be an object")
            continue
        incident_id = incident.get("incident_id")
        if not incident_id or incident_id in incident_ids:
            errors.append(f"incidents[{index}] has missing/duplicate incident_id")
        else:
            incident_ids.add(str(incident_id))
        status = incident.get("status")
        if status not in {"UNRECONCILED", "RECONCILED"}:
            errors.append(f"incidents[{index}] has invalid status {status}")
        reconciliation = incident.get("reconciliation")
        if status == "RECONCILED":
            if not isinstance(reconciliation, dict):
                errors.append(f"incidents[{index}] RECONCILED requires reconciliation object")
            else:
                evidence = reconciliation.get("evidence_refs")
                reviewer = reconciliation.get("reviewed_by")
                if reviewer != "main-reviewer":
                    errors.append(f"incidents[{index}] reconciliation must be reviewed_by main-reviewer")
                if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item for item in evidence):
                    errors.append(f"incidents[{index}] reconciliation requires non-empty evidence_refs")
    return errors


def unresolved_incidents(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in registry.get("incidents") or [] if item.get("status") == "UNRECONCILED"]


def cmd_scan(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    registry = _load(registry_path)
    errors = validate_registry(registry)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    token = args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    changes = fetch_changes(registry, token)
    updated = scan_registry(registry, _workstreams(ROOT), changes, now=args.now or _iso_now())
    _write(registry_path, updated)
    print(f"External ingress scan complete: {sum(len(v) for v in changes.values())} change(s) inspected; {len(unresolved_incidents(updated))} unresolved incident(s).")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    registry = _load(Path(args.registry))
    errors = validate_registry(registry)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    unresolved = unresolved_incidents(registry)
    for incident in unresolved:
        subject = f"PR #{incident['pull_request']}" if incident.get("pull_request") else str(incident.get("commit_sha"))[:12]
        print(
            f"UNRECONCILED: {incident.get('repository')} {subject} ({incident.get('incident_id')}). "
            "Main/Reviewer reconciliation evidence is required before canonical progress attribution.",
            file=sys.stderr,
        )
    return 1 if errors or unresolved else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect repository changes that bypass canonical claim/checkpoint evidence.")
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--token")
    scan.add_argument("--now")
    check = subparsers.add_parser("check")
    scan.set_defaults(func=cmd_scan)
    check.set_defaults(func=cmd_check)
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
