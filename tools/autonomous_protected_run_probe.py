"""Read-only retrieval of a protected GitHub workflow run.

Only API-fetched metadata is passed to the pure verifier. This does not
authenticate a receipt artifact or authorize a state transition.
"""
from __future__ import annotations

import re

from tools.autonomous_ci_probe import fetch_json
from tools.autonomous_protected_run import validate_protected_run

_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")

_ALLOWED_WORKFLOW = ".github/workflows/autonomous-ci-probe.yml"


def fetch_protected_run(repository: str, run_id: int, run_attempt: int,
                        workflow_path: str, protected_sha: str, token: str) -> dict:
    if not isinstance(repository, str) or not _REPO.fullmatch(repository):
        raise ValueError("invalid repository")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("invalid run ID")
    if type(run_attempt) is not int or run_attempt <= 0:
        raise ValueError("invalid run attempt")
    if workflow_path != _ALLOWED_WORKFLOW:
        raise ValueError("protected workflow is not allowlisted")
    if not isinstance(protected_sha, str) or not _SHA.fullmatch(protected_sha):
        raise ValueError("invalid protected SHA")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("GitHub token required")
    url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
    run = fetch_json(url, token)
    return validate_protected_run(
        run, repository=repository, workflow_path=workflow_path,
        head_sha=protected_sha, run_id=run_id, run_attempt=run_attempt,
    )
