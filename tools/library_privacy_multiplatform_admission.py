"""Admit real Linux/Windows/macOS Dart tests for the pinned Library candidate.

Only a protected same-run GitHub Actions writer may call this after ALL three
unprivileged matrix jobs succeeded. Receipts must come from that run's
download-artifact directories, and they must match the independently
recalculated source digest and preflight inventory.

This records tested OS targets, NOT runtime validation, a software-security
review, license authorization or catalog certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from library_evidence import EvidenceError, verify_manifest_evidence  # noqa: E402
from library_pipeline import (  # noqa: E402
    PipelineError, load_json, validate_payload, write_json,
)
from library_privacy_preflight import (  # noqa: E402
    CANDIDATE, PreflightError, security_preflight,
)

REPOSITORY = "pilialvu75-hue/AI-Orchestrator-Module-Library"
ASSET_ID = "diagnostics.logging.library.privacy_events"
VERSION = "0.1.0"
PLATFORMS = ("linux", "macos", "windows")
LEGACY_REPORT = "tests/dart-linux-ci-report.json"
REPORT = "tests/dart-cross-platform-ci-report.json"
SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
RECEIPT_SCHEMA = "ai-orchestrator.library-privacy-adversarial-test.v1"
REPORT_SCHEMA = "ai-orchestrator.library-test-report.v1"
CHECKS = [
    "dart analyze --fatal-infos",
    "dart run bin/self_test.dart",
    "dart tests/privacy_diagnostics_redaction_fuzz.dart",
]
RECEIPT_KEYS = {
    "schema", "asset_id", "version", "payload_sha256", "platform",
    "workflow_sha", "run_id", "run_attempt", "checked_source_files",
    "checks", "deterministic_adversarial_cases", "passed",
    "security_reviewed", "license_verified", "runtime_certified",
    "vulnerability_scanned",
}
MAX_EVIDENCE_BYTES = 64 * 1024


class PlatformAdmissionError(ValueError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise PlatformAdmissionError(message)


def _receipt(path: Path) -> tuple[dict, str]:
    require(not path.is_symlink() and path.is_file(),
            "platform CI evidence missing or symlinked")
    size = path.stat().st_size
    require(0 < size <= MAX_EVIDENCE_BYTES,
            "platform CI evidence empty or oversized")
    raw = path.read_bytes()
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PlatformAdmissionError("invalid platform CI JSON") from exc
    require(isinstance(obj, dict), "platform CI report must be a JSON object")
    return obj, hashlib.sha256(raw).hexdigest()


def admit_multiplatform(
    *, root: Path, artifacts: Path, workflow_sha: str,
    run_id: int, run_attempt: int,
    accepted_at: str | None = None,
) -> dict:
    require(isinstance(workflow_sha, str) and SHA.fullmatch(workflow_sha) is not None,
            "valid immutable workflow SHA required")
    require(type(run_id) is int and run_id > 0
            and type(run_attempt) is int and run_attempt > 0,
            "positive GitHub run ID and attempt required")
    require(artifacts.is_dir() and not artifacts.is_symlink(),
            "same-run artifact directory required")
    expected_dirs = {
        f"privacy-adversarial-{platform}-{run_id}" for platform in PLATFORMS
    }
    actual_dirs = set()
    for child in artifacts.iterdir():
        require(not child.is_symlink() and child.is_dir(),
                "artifact directory contains unexpected or linked entry")
        actual_dirs.add(child.name)
    require(actual_dirs == expected_dirs,
            "all three exact-run platform artifacts are required, with no extras")

    candidate = root / CANDIDATE
    manifest = load_json(candidate / "manifest.json")
    origin = manifest.get("provenance") or {}
    validation = manifest.get("validation") or {}
    security = manifest.get("security") or {}
    payload = manifest.get("payload") or {}
    require(manifest.get("id") == ASSET_ID and manifest.get("version") == VERSION,
            "candidate identity changed")
    require(manifest.get("status") == "tested"
            and validation.get("tests_passed") is True
            and security.get("reviewed") is False,
            "eligible tested candidate with pending security review required")
    require(origin.get("origin") == "built_in"
            and origin.get("source_repository") == f"https://github.com/{REPOSITORY}"
            and isinstance(origin.get("source_commit"), str)
            and SHA.fullmatch(origin["source_commit"]) is not None,
            "immutable built-in candidate provenance required")
    require(payload.get("type") == "repository_path"
            and payload.get("path") == "payload/src"
            and isinstance(payload.get("sha256"), str)
            and HASH.fullmatch(payload["sha256"]) is not None,
            "immutable local Dart payload required")
    require(manifest.get("platforms") in (
                ["linux"], list(PLATFORMS))
            and validation.get("validated_on") in (
                ["linux"], list(PLATFORMS))
            and validation.get("test_report") in (LEGACY_REPORT, REPORT),
            "candidate platform claims or report path changed")
    require((origin.get("license") in (None, "", "NOASSERTION"))
            and origin.get("license_file") is None,
            "license authority cannot be granted by cross-platform CI")
    validate_payload(manifest, candidate)
    verify_manifest_evidence(candidate, manifest)
    fresh = security_preflight(root)
    require(fresh.get("payload_tree_sha256") == payload["sha256"]
            and fresh.get("security_reviewed") is False
            and fresh.get("license_verified") is False
            and fresh.get("vulnerability_scanned") is False,
            "source preflight did not match source pin or pending approvals")

    platform_proofs: dict[str, dict] = {}
    for platform in PLATFORMS:
        directory = artifacts / f"privacy-adversarial-{platform}-{run_id}"
        require(not directory.is_symlink(), "platform artifact may not be a symlink")
        require({p.name for p in directory.iterdir()} ==
                {"privacy-target-evidence.json", "privacy-preflight.json"},
                "platform artifact must contain exact evidence and preflight files")
        receipt, receipt_hash = _receipt(directory / "privacy-target-evidence.json")
        preflight, preflight_hash = _receipt(directory / "privacy-preflight.json")
        require(set(receipt) == RECEIPT_KEYS
                and receipt.get("schema") == RECEIPT_SCHEMA
                and receipt.get("asset_id") == ASSET_ID
                and receipt.get("version") == VERSION
                and receipt.get("payload_sha256") == payload["sha256"]
                and receipt.get("platform") == platform
                and receipt.get("workflow_sha") == workflow_sha
                and type(receipt.get("run_id")) is int and receipt["run_id"] == run_id
                and type(receipt.get("run_attempt")) is int
                and receipt["run_attempt"] == run_attempt
                and receipt.get("checked_source_files") == fresh["source_files"]
                and receipt.get("checks") == CHECKS
                and type(receipt.get("deterministic_adversarial_cases")) is int
                and receipt["deterministic_adversarial_cases"] == 4096
                and receipt.get("passed") is True
                and receipt.get("security_reviewed") is False
                and receipt.get("license_verified") is False
                and receipt.get("runtime_certified") is False
                and receipt.get("vulnerability_scanned") is False,
                f"untrusted or mismatched {platform} adversarial CI receipt")
        require(preflight == fresh,
                f"{platform} preflight differs from recalculated pinned source")
        platform_proofs[platform] = {
            "artifact_name": f"privacy-adversarial-{platform}-{run_id}",
            "evidence_sha256": receipt_hash,
            "preflight_sha256": preflight_hash,
        }

    if validation["test_report"] == REPORT:
        existing = load_json(candidate / REPORT)
        require(existing.get("payload_sha256") == payload["sha256"]
                and existing.get("validated_on") == list(PLATFORMS)
                and existing.get("passed") is True
                and existing.get("security_certified") is False
                and existing.get("runtime_certified") is False,
                "existing multiplatform report is not valid")
        return {"asset": f"{ASSET_ID}@{VERSION}", "result": "already_tested",
                "validated_on": list(PLATFORMS), "certified": False}

    require(validation.get("test_report") == LEGACY_REPORT,
            "cannot replace unrecognized test report")
    output_path = candidate / REPORT
    require(not output_path.exists() and not output_path.is_symlink(),
            "preexisting cross-platform report cannot be overwritten")
    if accepted_at is None:
        accepted_at = datetime.now(timezone.utc).isoformat()
    try:
        when = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise PlatformAdmissionError("invalid evidence admission timestamp") from exc
    require(when.tzinfo is not None and when.utcoffset() is not None,
            "timestamp must be timezone-aware")
    report = {
        "schema": REPORT_SCHEMA,
        "asset_id": ASSET_ID,
        "version": VERSION,
        "source_commit": origin["source_commit"],
        "payload_sha256": payload["sha256"],
        "passed": True,
        "validated_on": list(PLATFORMS),
        "validated_at": when.isoformat(),
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "workflow_sha": workflow_sha,
        "workflow_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
        "checks": CHECKS,
        "deterministic_adversarial_cases_per_platform": 4096,
        "platform_proofs": platform_proofs,
        "scope": "Dart SDK self-test, analysis and adversarial redaction only",
        "score_basis": "existing_tested_floor_only_no_additional_certification",
        "security_certified": False,
        "license_verified": False,
        "runtime_certified": False,
    }
    write_json(output_path, report)
    manifest["platforms"] = list(PLATFORMS)
    manifest["validation"] = {
        **validation,
        "validated_on": list(PLATFORMS),
        "validated_at": when.isoformat(),
        "test_report": REPORT,
    }
    write_json(candidate / "manifest.json", manifest)
    verify_manifest_evidence(candidate, manifest)
    return {"asset": f"{ASSET_ID}@{VERSION}", "result": "tested_multiplatform",
            "validated_on": list(PLATFORMS), "certified": False,
            "workflow_run_id": run_id, "payload_sha256": payload["sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    args = parser.parse_args()
    try:
        result = admit_multiplatform(
            root=args.root, artifacts=args.artifacts,
            workflow_sha=args.workflow_sha, run_id=args.run_id,
            run_attempt=args.run_attempt,
        )
    except (OSError, ValueError, PipelineError, EvidenceError,
            PreflightError) as exc:
        print(f"multiplatform Dart admission refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
