"""Join independently fetched GitHub run evidence with canonical receipt identity.

Read-only: this validates consistency, NOT artifact authenticity or authority.
"""
from __future__ import annotations

from tools.autonomous_protected_run_probe import fetch_protected_run
from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_receipt_binding import validate_receipt_binding


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
    if (not isinstance(entries, list) or artifacts["total_count"] != len(entries)
            or artifacts["total_count"] > 100):
        raise ValueError("incomplete protected artifact listing")
    matching = [a for a in entries if isinstance(a, dict)
                and a.get("name") == "autonomous-ci-evidence"
                and a.get("expired") is False
                and (a.get("workflow_run") or {}).get("id") == run_id]
    if len(matching) != 1 or type(matching[0].get("id")) is not int or matching[0]["id"] <= 0:
        raise ValueError("missing or ambiguous protected CI artifact")
    return {
        "artifact_id": matching[0]["id"],
        "identity": identity,
        "protected_run": run,
        "trusted_receipt": False,
        "completion_authorized": False,
    }
