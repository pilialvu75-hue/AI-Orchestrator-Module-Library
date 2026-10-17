"""Join independently fetched GitHub run evidence with canonical receipt identity.

Read-only: this validates consistency, NOT artifact authenticity or authority.
"""
from __future__ import annotations

from tools.autonomous_protected_run_probe import fetch_protected_run
from tools.autonomous_receipt_binding import validate_receipt_binding


def probe_receipt_evidence(*, receipt: dict, canonical_identity: dict,
                           protected_repository: str, run_id: int,
                           run_attempt: int, workflow_path: str,
                           protected_sha: str, github_token: str) -> dict:
    identity = validate_receipt_binding(receipt, canonical_identity)
    run = fetch_protected_run(
        protected_repository, run_id, run_attempt, workflow_path,
        protected_sha, github_token,
    )
    if run["repository"] != protected_repository or run["head_sha"] != protected_sha:
        raise ValueError("protected run metadata mismatch")
    return {
        "identity": identity,
        "protected_run": run,
        "trusted_receipt": False,
        "completion_authorized": False,
    }
