"""Join independently fetched GitHub run evidence with canonical receipt identity.

Read-only: this validates consistency, NOT artifact authenticity or authority.
"""
from __future__ import annotations

import io
import json
import urllib.request
import zipfile

from tools.autonomous_protected_run_probe import fetch_protected_run
from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_receipt_binding import validate_receipt_binding
from tools.autonomous_canonical_identity import derive_canonical_receipt_identity


def fetch_ci_evidence_artifact(repository: str, artifact_id: int, token: str) -> dict:
    """Read the single JSON entry in a small GitHub Actions artifact ZIP."""
    if (not isinstance(repository, str) or repository.count("/") != 1
            or any(not part or part in (".", "..") or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._" for c in part)
                   for part in repository.split("/"))):
        raise ValueError("invalid artifact repository")
    if type(artifact_id) is not int or artifact_id <= 0:
        raise ValueError("invalid artifact ID")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("GitHub token required")
    url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}/zip"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "airlab-autonomous-receipt-probe",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(262145)
    if len(data) > 262144:
        raise ValueError("protected artifact exceeds size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = archive.infolist()
            if len(files) != 1 or files[0].filename != "ci-evidence.json":
                raise ValueError("unexpected protected artifact entries")
            if files[0].is_dir() or files[0].flag_bits & 1:
                raise ValueError("encrypted or directory artifact entry rejected")
            if files[0].file_size > 65536:
                raise ValueError("protected evidence JSON exceeds size limit")
            with archive.open(files[0]) as entry:
                payload = entry.read(65537)
            if len(payload) > 65536:
                raise ValueError("protected evidence decompression exceeds size limit")
        result = json.loads(payload)
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise ValueError("invalid protected evidence artifact") from exc
    if not isinstance(result, dict):
        raise ValueError("protected evidence must be an object")
    return result


def probe_receipt_evidence(*, receipt: dict, canonical_identity: dict,
                           protected_repository: str, run_id: int,
                           run_attempt: int, workflow_path: str,
                           protected_sha: str, github_token: str) -> dict:
    # Canonical identity must be supplied by a trusted snapshot, never by the worker.
    identity = validate_receipt_binding(receipt, canonical_identity)
    if identity["repository"] != protected_repository:
        raise ValueError("protected repository does not match canonical receipt identity")
    run = fetch_protected_run(
        protected_repository, run_id, run_attempt, workflow_path,
        protected_sha, github_token,
    )
    if (not isinstance(run, dict)
            or run.get("repository") != protected_repository
            or run.get("head_sha") != protected_sha
            or run.get("run_id") != run_id
            or run.get("run_attempt") != run_attempt
            or run.get("workflow_path") != workflow_path
            or run.get("authenticated") is not False
            or run.get("completion_authorized") is not False):
        raise ValueError("protected run metadata mismatch")
    artifacts = fetch_json(
        f"https://api.github.com/repos/{protected_repository}/actions/runs/{run_id}/artifacts?per_page=100",
        github_token,
    )
    if not isinstance(artifacts, dict) or type(artifacts.get("total_count")) is not int:
        raise ValueError("invalid protected artifact response")
    entries = artifacts.get("artifacts")
    if (not isinstance(entries, list) or artifacts["total_count"] < 0
            or artifacts["total_count"] != len(entries)
            or artifacts["total_count"] > 100):
        raise ValueError("incomplete protected artifact listing")
    if type(run_id) is not int or run_id <= 0 or type(run_attempt) is not int or run_attempt <= 0:
        raise ValueError("invalid protected run identity")
    matching = [a for a in entries if isinstance(a, dict)
                and a.get("name") == "autonomous-ci-evidence"
                and a.get("expired") is False
                and isinstance(a.get("workflow_run"), dict)
                and type(a["workflow_run"].get("id")) is int
                and a["workflow_run"]["id"] == run_id]
    if len(matching) != 1 or type(matching[0].get("id")) is not int or matching[0]["id"] <= 0:
        raise ValueError("missing or ambiguous protected CI artifact")
    artifact_run = matching[0]["workflow_run"]
    if not isinstance(artifact_run, dict):
        raise ValueError("invalid protected artifact workflow metadata")
    if (artifact_run.get("head_sha") != protected_sha
            or artifact_run.get("head_branch") != "main"
            or type(artifact_run.get("repository_id")) is not int
            or artifact_run["repository_id"] <= 0
            or type(artifact_run.get("head_repository_id")) is not int
            or artifact_run["head_repository_id"] != artifact_run["repository_id"]):
        raise ValueError("protected artifact provenance metadata mismatch")
    evidence = fetch_ci_evidence_artifact(protected_repository, matching[0]["id"], github_token)
    if (not isinstance(evidence, dict)
            or evidence.get("repository") != identity["repository"]
            or type(evidence.get("pr_number")) is not int
            or evidence["pr_number"] != identity["pr_number"]
            or evidence.get("head_sha") != identity["head_sha"]
            or type(evidence.get("protected_run_id")) is not int
            or evidence["protected_run_id"] != run_id
            or type(evidence.get("protected_run_attempt")) is not int
            or evidence["protected_run_attempt"] != run_attempt
            or evidence.get("protected_workflow_ref") != f"{protected_repository}/{workflow_path}@refs/heads/main"
            or evidence.get("trusted_receipt") is not False
            or evidence.get("completion_authorized") is not False
            or set(evidence) != {"repository", "pr_number", "head_sha", "verified_checks",
                                 "protected_run_id", "protected_run_attempt", "protected_workflow_ref",
                                 "trusted_receipt", "completion_authorized"}
            or not isinstance(evidence.get("verified_checks"), dict)
            or not evidence["verified_checks"]
            or any(not isinstance(name, str) or not name.strip()
                   or type(check_id) is not int or check_id <= 0
                   for name, check_id in evidence["verified_checks"].items())):
        raise ValueError("protected CI evidence does not match canonical identity")
    # A workflow artifact is not a completion credential. Independently
    # re-fetch the PR/check evidence and compare its exact check-run IDs.
    from tools.autonomous_ci_probe import probe as probe_live_ci
    live = probe_live_ci(
        identity["repository"], identity["pr_number"],
        sorted(evidence["verified_checks"]), github_token,
    )
    if (not isinstance(live, dict)
            or live.get("repository") != identity["repository"]
            or live.get("pr_number") != identity["pr_number"]
            or live.get("head_sha") != identity["head_sha"]
            or live.get("verified_checks") != evidence["verified_checks"]):
        raise ValueError("protected CI artifact differs from independently verified live checks")
    return {
        "ci_evidence": evidence,
        "artifact_id": matching[0]["id"],
        "identity": identity,
        "protected_run": run,
        "trusted_receipt": False,
        "completion_authorized": False,
    }


def probe_canonical_receipt_evidence(*, lane: dict, github_pr: dict,
                                     receipt: dict, protected_repository: str,
                                     run_id: int, run_attempt: int,
                                     workflow_path: str, protected_sha: str,
                                     github_token: str) -> dict:
    """Bind evidence to canonical lane and independently fetched PR metadata.

    The caller must obtain lane from the protected canonical snapshot and github_pr
    from the GitHub API, never from worker-provided request fields. Read-only.
    """
    identity = derive_canonical_receipt_identity(lane, github_pr)
    return probe_receipt_evidence(
        receipt=receipt, canonical_identity=identity,
        protected_repository=protected_repository, run_id=run_id,
        run_attempt=run_attempt, workflow_path=workflow_path,
        protected_sha=protected_sha, github_token=github_token,
    )
