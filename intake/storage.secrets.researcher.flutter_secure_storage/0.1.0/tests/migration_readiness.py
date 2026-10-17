"""Offline, fail-closed review gate for the existing Android secret-store upgrade.

A static JSON report never authorizes runtime migration or Library certification.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_GATES = frozenset({
    "verify_initial_secret_presence",
    "preupgrade_cipher_migration",
    "non_destructive_restore",
    "biometric_and_keychain_errors",
    "upgrade_rollback",
    "android_physical_gate",
    "desktop_platform_gates",
    "library_contract_and_security_review",
})
EXPECTED_CONSUMERS = frozenset({
    "cloud_credentials",
    "workshop_github_auth",
    "module_library_github_config",
    "diagnostics_github_token",
})
COMMIT = "e8eeb449cd512b26153f0a3376dfe374dd39a999"


def _major(version: object) -> int | None:
    match = re.fullmatch(r"([0-9]+)\.[0-9]+\.[0-9]+", str(version))
    return int(match.group(1)) if match else None


def assess(manifest: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    blockers: set[str] = set()
    if manifest.get("id") != "storage.secrets.researcher.flutter_secure_storage":
        blockers.add("INVALID_CANDIDATE_ID")
    if manifest.get("provenance", {}).get("source_commit") != COMMIT:
        blockers.add("SOURCE_COMMIT_MISMATCH")
    if evidence.get("candidate", {}).get("source_commit") != COMMIT:
        blockers.add("EVIDENCE_COMMIT_MISMATCH")
    if evidence.get("source_control", {}).get("stage") != manifest.get("status"):
        blockers.add("LIFECYCLE_STATE_MISMATCH")
    if evidence.get("candidate", {}).get("library_certified") is not False:
        blockers.add("CERTIFICATION_FLAG_INVALID")
    if evidence.get("source_control", {}).get("certification_allowed") is not False:
        blockers.add("UNAUTHORIZED_CERTIFICATION_FLAG")
    if evidence.get("source_control", {}).get("merge_allowed") is not False:
        blockers.add("UNAUTHORIZED_MERGE_FLAG")
    if manifest.get("validation", {}).get("tests_passed") is not False:
        blockers.add("UNVERIFIED_TEST_CLAIM")
    if manifest.get("security", {}).get("reviewed") is not False:
        blockers.add("UNVERIFIED_SECURITY_REVIEW_CLAIM")

    previous = _major(evidence.get("source_app", {}).get("resolved_version"))
    proposed = _major(evidence.get("candidate", {}).get("package_version"))
    if previous is None or proposed is None or proposed <= previous:
        blockers.add("INVALID_MAJOR_UPGRADE_BASELINE")
    if evidence.get("source_app", {}).get("declared_constraint") != "^10.3.1":
        blockers.add("BASELINE_CONSTRAINT_DRIFT")

    consumers = evidence.get("secret_consumer_inventory")
    if not isinstance(consumers, list):
        consumers = []
    names = [c.get("consumer") for c in consumers if isinstance(c, dict)]
    if len(names) != len(EXPECTED_CONSUMERS) or set(names) != EXPECTED_CONSUMERS:
        blockers.add("CREDENTIAL_CONSUMER_INVENTORY_INCOMPLETE")
    if any(not isinstance(c, dict) or
           c.get("state") != "PENDING_MIGRATION_VALIDATION" for c in consumers):
        blockers.add("CONSUMER_MIGRATION_EVIDENCE_NOT_VERIFIED")

    rows = evidence.get("acceptance_gates")
    if not isinstance(rows, list):
        rows = []
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict)}
    if len(by_id) != len(rows) or set(by_id) != EXPECTED_GATES:
        blockers.add("MIGRATION_GATES_INCOMPLETE")
    pending = sorted(
        gate for gate in EXPECTED_GATES
        if by_id.get(gate, {}).get("state") != "PASS"
    )
    if pending:
        blockers.add("MIGRATION_EVIDENCE_PENDING")

    # JSON flags alone cannot attest physical-device tests or independent review.
    # Even an all-PASS self-report MUST stop at independent verification.
    return {
        "schema": "ai-orchestrator.storage-secrets-migration-readiness.v1",
        "state": "BLOCKED" if blockers else "INDEPENDENT_REVIEW_REQUIRED",
        "blockers": sorted(blockers),
        "pending_gates": pending,
        "source_commit": COMMIT,
        "package_versions": {
            "existing": evidence.get("source_app", {}).get("resolved_version"),
            "candidate": evidence.get("candidate", {}).get("package_version"),
        },
        "library_certified": False,
        "runtime_upgrade_authorized": False,
        "secrets_read": False,
        "untrusted_code_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = assess(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.evidence.read_text(encoding="utf-8")),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
