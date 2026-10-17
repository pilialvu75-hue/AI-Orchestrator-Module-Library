"""Independent, read-only audit of the Library CI gate evidence.

A successful GitHub check is necessary but not enough for autonomous promotion:
this module pins the trusted validation workflow and confirms each expected
job step at the exact PR head. It NEVER approves implementation, integration,
or target-runtime behaviour.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from tools.autonomous_ci_probe import fetch_json

LIBRARY_REPOSITORY = "pilialvu75-hue/AI-Orchestrator-Module-Library"
VALIDATE_WORKFLOW = ".github/workflows/validate-library.yml"
CHECK_NAME = "validate"
REQUIRED_STEPS = (
    "Validate canonical control plane",
    "Validate catalog, needs and module contracts",
    "Validate version history and observations",
    "Validate lifecycle ledger and availability state",
    "Run Library tests",
    "Export deterministic offline Library snapshot",
    "Validate offline snapshot",
)
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _strict_listing(response: dict, collection: str) -> list:
    if not isinstance(response, dict):
        raise ValueError("GitHub response must be an object")
    total = response.get("total_count")
    items = response.get(collection)
    if type(total) is not int or total < 0 or total > 100:
        raise ValueError("incomplete GitHub audit listing")
    if not isinstance(items, list) or len(items) != total:
        raise ValueError("GitHub audit listing count mismatch")
    return items


def _trusted_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def audit_library_ci_gates(
    identity: dict, ci_evidence: dict, github_token: str, *,
    trusted_root: Path,
) -> dict:
    """Verify the CI job independently; all non-CI promotion gates remain open.

    trusted_root must be the protected default-branch checkout at the workflow
    run's pinned SHA. The caller must already have validated canonical lane
    identity and claim expiry; this function does not confer mutation rights.
    """
    if (not isinstance(identity, dict)
            or identity.get("repository") != LIBRARY_REPOSITORY
            or type(identity.get("pr_number")) is not int
            or identity["pr_number"] <= 0
            or not isinstance(identity.get("head_sha"), str)
            or not _SHA.fullmatch(identity["head_sha"])):
        raise ValueError("unsupported or malformed canonical audit identity")
    if not isinstance(ci_evidence, dict) or (
        ci_evidence.get("repository") != LIBRARY_REPOSITORY
        or ci_evidence.get("pr_number") != identity["pr_number"]
        or ci_evidence.get("head_sha") != identity["head_sha"]
        or ci_evidence.get("trusted_receipt") is not False
        or ci_evidence.get("completion_authorized") is not False
    ):
        raise ValueError("CI evidence is not bound to the canonical PR")
    verified = ci_evidence.get("verified_checks")
    if (not isinstance(verified, dict) or set(verified) != {CHECK_NAME}
            or type(verified[CHECK_NAME]) is not int
            or verified[CHECK_NAME] <= 0):
        raise ValueError("independent gate audit requires the exact Library validate check")
    if not isinstance(github_token, str) or not github_token.strip():
        raise ValueError("GitHub token required for independent gate audit")
    if not isinstance(trusted_root, Path):
        raise ValueError("trusted checkout root required")

    sha = identity["head_sha"]
    base = f"https://api.github.com/repos/{LIBRARY_REPOSITORY}"
    trusted_sha = _trusted_blob_sha(trusted_root / VALIDATE_WORKFLOW)
    source = fetch_json(f"{base}/contents/{VALIDATE_WORKFLOW}?ref={sha}", github_token)
    if (not isinstance(source, dict)
            or source.get("type") != "file"
            or source.get("sha") != trusted_sha):
        raise ValueError("PR validation workflow differs from protected default-branch policy")

    runs = _strict_listing(
        fetch_json(f"{base}/actions/runs?head_sha={sha}&per_page=100", github_token),
        "workflow_runs",
    )
    check_id = verified[CHECK_NAME]
    expected_check_url = f"{base}/check-runs/{check_id}"
    matches = []
    for run in runs:
        if (not isinstance(run, dict)
                or run.get("head_sha") != sha
                or run.get("path") != VALIDATE_WORKFLOW
                or run.get("event") != "pull_request"
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or (run.get("repository") or {}).get("full_name") != LIBRARY_REPOSITORY
                or type(run.get("id")) is not int or run["id"] <= 0):
            continue
        jobs = _strict_listing(
            fetch_json(f"{base}/actions/runs/{run['id']}/jobs?per_page=100", github_token),
            "jobs",
        )
        for job in jobs:
            if isinstance(job, dict) and job.get("check_run_url") == expected_check_url:
                matches.append((run, job))
    if len(matches) != 1:
        raise ValueError("required Library CI job missing or ambiguous")
    run, job = matches[0]
    if (job.get("name") != CHECK_NAME or job.get("head_sha") != sha
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
            or job.get("run_id") != run["id"]):
        raise ValueError("Library CI job metadata does not match successful run")
    steps = job.get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ValueError("Library CI job steps are malformed")
    for name in REQUIRED_STEPS:
        matches_for_step = [step for step in steps if step.get("name") == name]
        if (len(matches_for_step) != 1
                or matches_for_step[0].get("status") != "completed"
                or matches_for_step[0].get("conclusion") != "success"):
            raise ValueError(f"required Library CI gate step missing or unsuccessful: {name}")

    return {
        "schema_version": 1,
        "canonical_identity": identity,
        "workflow_blob_sha": trusted_sha,
        "workflow_run_id": run["id"],
        "check_run_id": check_id,
        "validated_steps": list(REQUIRED_STEPS),
        "gate_assessment": {
            "G0_CLAIM": "CANONICAL_LIVE_CLAIM_VERIFIED_BY_CALLER",
            "G1_IMPLEMENTATION": "PENDING_INDEPENDENT_IMPLEMENTATION_REVIEW",
            "G2_STATIC": "CI_PIPELINE_STEPS_VERIFIED",
            "G3_CI": "EXACT_HEAD_SUCCESS_VERIFIED",
            "G4_INTEGRATION": "CI_CONTRACT_CHECKS_VERIFIED_REVIEW_PENDING",
            "G5_TARGET_RUNTIME": "REQUIRES_INDEPENDENT_RUNTIME_APPLICABILITY_ASSESSMENT",
        },
        "completion_authorized": False,
        "trusted_receipt": False,
    }
