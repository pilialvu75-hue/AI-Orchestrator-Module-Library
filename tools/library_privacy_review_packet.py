"""Deterministic review handoff for the tested, not-certified Dart candidate.

This tool inventories the pinned bytes and already recorded OS test receipts.
It is a source-bound *review request*, never an approval or license grant.
The protected certifier MUST NOT infer security.reviewed from this JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from library_evidence import EvidenceError, verify_test_evidence
from library_privacy_preflight import (
    ASSET_ID, CANDIDATE, VERSION, PreflightError, security_preflight,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_EXPECTED_TARGETS = frozenset({"linux", "macos", "windows"})
_REPORT = "tests/dart-cross-platform-ci-report.json"


class ReviewPacketError(ValueError):
    pass


def _require(ok: bool, detail: str) -> None:
    if not ok:
        raise ReviewPacketError(detail)


def _object(path: Path, description: str) -> dict:
    _require(path.is_file() and not path.is_symlink(), f"{description} missing or symlinked")
    _require(path.stat().st_size < 1024 * 1024, f"{description} is oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, OSError, json.JSONDecodeError) as exc:
        raise ReviewPacketError(f"{description} invalid JSON") from exc
    _require(isinstance(value, dict), f"{description} must be an object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_review_packet(root: Path) -> dict:
    root = root.resolve()
    base = root / CANDIDATE
    manifest_path = base / "manifest.json"
    manifest = _object(manifest_path, "candidate manifest")
    _require(manifest.get("id") == ASSET_ID and manifest.get("version") == VERSION,
             "candidate identity changed")
    _require(manifest.get("status") == "tested", "candidate has no validated tested state")
    _require((manifest.get("security") or {}).get("reviewed") is False,
             "an already approved review cannot be self-certified here")
    _require((manifest.get("validation") or {}).get("tests_passed") is True,
             "tested candidate lacks test evidence")
    try:
        verify_test_evidence(base, manifest)
        preflight = security_preflight(root)
    except (EvidenceError, PreflightError) as exc:
        raise ReviewPacketError(f"pinned candidate verification failed: {exc}") from exc

    source_pin = preflight["payload_tree_sha256"]
    _require(isinstance(source_pin, str) and _SHA256.fullmatch(source_pin) is not None,
             "pinned source SHA256 missing")
    report_path = base / _REPORT
    report = _object(report_path, "three-platform test report")
    _require(report.get("schema") == "ai-orchestrator.library-test-report.v1",
             "unsupported test report schema")
    _require(report.get("asset_id") == ASSET_ID and report.get("version") == VERSION,
             "three-platform test report identity differs from candidate")
    source_commit = (manifest.get("provenance") or {}).get("source_commit")
    _require(isinstance(source_commit, str) and _SHA40.fullmatch(source_commit) is not None,
             "candidate source commit must be fully pinned")
    _require(report.get("source_commit") == source_commit,
             "source commit in test report differs")
    _require(report.get("payload_sha256") == source_pin,
             "test report source digest differs")
    _require(report.get("passed") is True, "three-platform test report is not passing")
    _require(set(report.get("validated_on") or []) == _EXPECTED_TARGETS
             and len(report.get("validated_on") or []) == len(_EXPECTED_TARGETS),
             "three-platform test report must contain exactly Linux, macOS, Windows")
    _require(set((manifest.get("validation") or {}).get("validated_on") or []) == _EXPECTED_TARGETS,
             "manifest and three-platform test targets differ")
    _require(report.get("runtime_certified") is False
             and report.get("security_certified") is False
             and report.get("license_verified") is False,
             "untrusted test report claims review or runtime authority")
    _require(type(report.get("workflow_run_id")) is int and report["workflow_run_id"] > 0,
             "CI workflow run ID missing")
    _require(type(report.get("workflow_run_attempt")) is int
             and report["workflow_run_attempt"] > 0,
             "CI run attempt missing")
    _require(isinstance(report.get("workflow_sha"), str)
             and _SHA40.fullmatch(report["workflow_sha"]) is not None,
             "CI workflow revision is not pinned")
    _require(type(report.get("deterministic_adversarial_cases_per_platform")) is int
             and report["deterministic_adversarial_cases_per_platform"] >= 1,
             "adversarial test count is not recorded")
    proof_by_platform = report.get("platform_proofs")
    _require(isinstance(proof_by_platform, dict)
             and set(proof_by_platform) == _EXPECTED_TARGETS,
             "three-platform artifacts missing or duplicated")
    checks = report.get("checks")
    _require(isinstance(checks, list)
             and {"dart analyze --fatal-infos", "dart run bin/self_test.dart",
                  "dart tests/privacy_diagnostics_redaction_fuzz.dart"}.issubset(set(checks)),
             "Dart CI report lacks required checks")
    proofs = []
    for platform in sorted(_EXPECTED_TARGETS):
        proof = proof_by_platform[platform]
        _require(isinstance(proof, dict), "invalid platform proof record")
        _require(proof.get("artifact_name")
                 == f"privacy-adversarial-{platform}-{report['workflow_run_id']}",
                 f"{platform} artifact name is not tied to the exact run")
        for field in ("evidence_sha256", "preflight_sha256"):
            value = proof.get(field)
            _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None,
                     f"{platform} {field} is not a full immutable digest")
        proofs.append({"platform": platform, **proof})

    # An artifact name or hash stored in Git cannot prove that GitHub actually
    # ran the checks or that the uploader was a trusted independent authority.
    # The human/independent verifier must fetch these artifacts separately.
    license_data = manifest.get("provenance") or {}
    result = {
        "schema": "ai-orchestrator.library-privacy-review-request.v1",
        "asset_id": ASSET_ID,
        "version": VERSION,
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "source": {
            "repository": license_data.get("source_repository"),
            "commit": source_commit,
            "tree_sha256": source_pin,
            "manifest_sha256": _sha(manifest_path),
            "files": preflight["source_files"],
            "declared_dependencies": preflight["third_party_pub_dependencies"],
        },
        "test_claims_to_verify_independently": {
            "report_sha256": _sha(report_path),
            "run_id": report["workflow_run_id"],
            "run_attempt": report["workflow_run_attempt"],
            "workflow_sha": report["workflow_sha"],
            "checks": sorted(set(checks)),
            "adversarial_cases_per_platform": report["deterministic_adversarial_cases_per_platform"],
            "artifacts": proofs,
            "github_workflow_verified": False,
        },
        "license_review": {
            "declared_license": license_data.get("license"),
            "declared_license_file": license_data.get("license_file"),
            "rights_granted_or_verified": False,
            "action": "Confirm rights holder and attributable license, or explicit scoped permission.",
        },
        "security_review": {
            "sbom": preflight["sbom"],
            "source_imports_policy": preflight["dart_imports_policy"],
            "known_declared_third_party_packages": preflight["third_party_pub_dependencies"],
            "actual_vulnerability_scan_complete": False,
            "reviewed_by_independent_authority": False,
            "action": "Verify pinned CI artifacts from GitHub and inspect source and dependency/SBOM evidence.",
        },
        "scope": {
            "verified_runtime_targets": [],
            "tested_dart_sdk_hosts_claimed": sorted(_EXPECTED_TARGETS),
            "contract_integration_verified": False,
            "transport_persistence_reviewed": False,
        },
        "security_reviewed": False,
        "license_verified": False,
        "module_certification_authorized": False,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = build_review_packet(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Pinned Dart candidate review request generated; certification_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
