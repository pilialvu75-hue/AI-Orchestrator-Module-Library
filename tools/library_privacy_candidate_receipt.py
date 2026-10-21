"""Accept real Dart CI evidence as a *tested* Library intake, never certification.

The writer runs only after an unprivileged GitHub Actions job has successfully
analyzed and executed the pinned source. It verifies the payload digest and
workflow run identity again before applying the ordinary lifecycle transitions.
No G6, runtime or security-review approval is produced by this module.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from library_evidence import EvidenceError, verify_manifest_evidence  # noqa: E402
from library_pipeline import (  # noqa: E402
    AssetRef, PipelineError, load_json, payload_tree_sha256, transition_intake, validate_payload,
    write_json,
)

ASSET_ID = "diagnostics.logging.library.privacy_events"
VERSION = "0.1.0"
REPOSITORY = "pilialvu75-hue/AI-Orchestrator-Module-Library"
RECEIPT_SCHEMA = "ai-orchestrator.privacy-candidate-test-receipt.v1"
TEST_SCHEMA = "ai-orchestrator.library-test-report.v1"
CHECKS = ["dart analyze --fatal-infos", "dart run bin/self_test.dart"]
SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
REPORT_REL = "tests/dart-linux-ci-report.json"


class ReceiptError(ValueError):
    pass


def _receipt(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ReceiptError("missing, linked, or oversized CI receipt")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("invalid CI receipt JSON") from exc
    if not isinstance(value, dict):
        raise ReceiptError("CI receipt must be a JSON object")
    return value


def accept_receipt(
    *, root: Path, path: Path, workflow_sha: str,
    workflow_run_id: int, workflow_run_attempt: int,
) -> dict:
    receipt = _receipt(path)
    base = root / "intake" / ASSET_ID / VERSION
    manifest = load_json(base / "manifest.json")
    origin = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    validation = manifest.get("validation") or {}
    security = manifest.get("security") or {}
    if (manifest.get("id") != ASSET_ID
            or manifest.get("version") != VERSION
            or manifest.get("capabilities") != ["diagnostics.logging"]
            or manifest.get("platforms") not in (["linux"], ["linux", "macos", "windows"])
            or origin.get("origin") != "built_in"
            or origin.get("source_repository") != f"https://github.com/{REPOSITORY}"
            or not isinstance(origin.get("source_commit"), str)
            or not SHA.fullmatch(origin["source_commit"])
            or security.get("reviewed") is not False
            or manifest.get("status") not in (
                "discovered", "quarantined", "normalized", "tested"
            )):
        raise ReceiptError("candidate origin, platform, review or lifecycle changed")
    validate_payload(manifest, base)
    if (payload.get("type") != "repository_path"
            or payload.get("path") != "payload/src"
            or not isinstance(payload.get("sha256"), str)
            or not HASH.fullmatch(payload["sha256"])
            or payload_tree_sha256(base / payload["path"]) != payload["sha256"]):
        raise ReceiptError("source bytes do not match immutable manifest digest")
    if (not isinstance(workflow_sha, str) or not SHA.fullmatch(workflow_sha)
            or type(workflow_run_id) is not int or workflow_run_id <= 0
            or type(workflow_run_attempt) is not int
            or workflow_run_attempt <= 0):
        raise ReceiptError("invalid protected workflow identity")
    if (set(receipt) != {
            "schema", "repository", "workflow_sha", "workflow_run_id",
            "workflow_run_attempt", "asset_id", "version", "source_commit",
            "payload_sha256", "validated_at", "checks", "validated_on", "passed"
    } or receipt.get("schema") != RECEIPT_SCHEMA
            or receipt.get("repository") != REPOSITORY
            or receipt.get("workflow_sha") != workflow_sha
            or receipt.get("workflow_run_id") != workflow_run_id
            or receipt.get("workflow_run_attempt") != workflow_run_attempt
            or receipt.get("asset_id") != ASSET_ID
            or receipt.get("version") != VERSION
            or receipt.get("source_commit") != origin["source_commit"]
            or receipt.get("payload_sha256") != payload["sha256"]
            or receipt.get("validated_on") != ["linux"]
            or receipt.get("checks") != CHECKS
            or receipt.get("passed") is not True):
        raise ReceiptError("CI receipt not bound to exact source, run and checks")
    try:
        when = datetime.fromisoformat(str(receipt["validated_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptError("invalid validation timestamp") from exc
    if when.tzinfo is None or when.utcoffset() is None:
        raise ReceiptError("validation timestamp must contain timezone")

    if manifest["status"] == "tested":
        if validation.get("test_report") == "tests/dart-cross-platform-ci-report.json":
            if (manifest.get("platforms") != ["linux", "macos", "windows"]
                    or validation.get("validated_on") != ["linux", "macos", "windows"]):
                raise ReceiptError("multiplatform tested candidate has inconsistent targets")
            verify_manifest_evidence(base, manifest)
            return {"asset": f"{ASSET_ID}@{VERSION}", "result": "already_tested_multiplatform"}
        report = load_json(base / REPORT_REL)
        if (report.get("workflow_sha") != workflow_sha
                or report.get("workflow_run_id") != workflow_run_id
                or report.get("payload_sha256") != payload["sha256"]):
            raise ReceiptError("already tested candidate has different evidence")
        verify_manifest_evidence(base, manifest)
        return {"asset": f"{ASSET_ID}@{VERSION}", "result": "already_tested"}

    # The reporting floor is the Library's 0.80 tested-stage gate, not a
    # performance/security/runtime quality score.
    report = {
        "schema": TEST_SCHEMA,
        "asset_id": ASSET_ID,
        "version": VERSION,
        "source_commit": origin["source_commit"],
        "passed": True,
        "validated_on": ["linux"],
        "validated_at": receipt["validated_at"],
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "workflow_sha": workflow_sha,
        "workflow_url": (
            f"https://github.com/{REPOSITORY}/actions/runs/{workflow_run_id}"
        ),
        "payload_sha256": payload["sha256"],
        "checks": CHECKS,
        "score_basis": "policy_floor_0.80_for_dart_analyze_and_functional_selftest_only",
        "runtime_certified": False,
        "security_certified": False,
    }
    if manifest["status"] == "discovered":
        manifest = transition_intake(root, AssetRef(ASSET_ID, VERSION), "quarantined")
    if manifest["status"] == "quarantined":
        manifest = transition_intake(root, AssetRef(ASSET_ID, VERSION), "normalized")
    if manifest["status"] != "normalized":
        raise ReceiptError("candidate must reach normalized state before test receipt")
    destination = base / REPORT_REL
    if destination.is_symlink() or destination.exists():
        raise ReceiptError("preexisting or linked test report cannot be overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, report)
    manifest["validation"] = {
        **validation,
        "score": 0.8,
        "tests_passed": True,
        "test_report": REPORT_REL,
        "validated_at": receipt["validated_at"],
        "validated_on": ["linux"],
    }
    write_json(base / "manifest.json", manifest)
    tested = transition_intake(root, AssetRef(ASSET_ID, VERSION), "tested")
    if (tested["status"] != "tested"
            or tested.get("security", {}).get("reviewed") is not False):
        raise ReceiptError("test receipt unexpectedly altered certification gates")
    verify_manifest_evidence(base, tested)
    return {
        "asset": f"{ASSET_ID}@{VERSION}",
        "result": "tested",
        "workflow_sha": workflow_sha,
        "workflow_run_id": workflow_run_id,
        "payload_sha256": payload["sha256"],
        "security_certified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    args = parser.parse_args()
    try:
        result = accept_receipt(
            root=args.root,
            path=args.receipt,
            workflow_sha=args.workflow_sha,
            workflow_run_id=args.run_id,
            workflow_run_attempt=args.run_attempt,
        )
    except (OSError, ReceiptError, ValueError, PipelineError, EvidenceError) as exc:
        print(f"privacy candidate test admission refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
