"""Validate protected workflow-run provenance; never authorize completion alone.

Call only with run metadata fetched independently from the GitHub API.
Worker-supplied JSON or a matching run ID is not authenticated evidence.
"""
from __future__ import annotations

def validate_protected_run(run: dict, *, repository: str, workflow_path: str,
                           head_sha: str, run_id: int, run_attempt: int) -> dict:
    if not isinstance(run, dict):
        raise ValueError("protected workflow run must be an object")
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise ValueError("invalid canonical repository")
    if (not isinstance(workflow_path, str) or not workflow_path.startswith(".github/workflows/")
            or not workflow_path.endswith((".yml", ".yaml"))
            or ".." in workflow_path or "\\" in workflow_path
            or any(c.isspace() for c in workflow_path)):
        raise ValueError("invalid protected workflow path")
    if type(run_id) is not int or run_id <= 0 or type(run_attempt) is not int or run_attempt <= 0:
        raise ValueError("invalid protected run identity")
    if type(run.get("id")) is not int or run["id"] != run_id:
        raise ValueError("protected run ID mismatch")
    if type(run.get("run_attempt")) is not int or run["run_attempt"] != run_attempt:
        raise ValueError("protected run attempt mismatch")
    if (run.get("repository") or {}).get("full_name") != repository:
        raise ValueError("protected run repository mismatch")
    if run.get("path") != workflow_path:
        raise ValueError("protected workflow identity mismatch")
    if run.get("head_branch") != "main" or run.get("event") != "workflow_dispatch":
        raise ValueError("protected run must execute on default branch")
    if not isinstance(head_sha, str) or len(head_sha) != 40 or any(c not in "0123456789abcdef" for c in head_sha):
        raise ValueError("invalid protected commit SHA")
    if run.get("head_sha") != head_sha:
        raise ValueError("protected run commit mismatch")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("protected run not successful")
    return {"run_id": run_id, "run_attempt": run_attempt, "workflow_path": workflow_path,
            "repository": repository, "head_sha": head_sha, "authenticated": False,
            "completion_authorized": False}
