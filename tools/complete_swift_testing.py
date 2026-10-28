"""Independent GitHub-job verification before advancing native Swift intake to TESTED.

Does not execute untrusted code, grant security review, certify or export.
One source-bound candidate per invocation; all authorization data comes from
GitHub Actions API rather than a worker-written PASS flag.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from library_evidence import verify_manifest_evidence
from library_intake_readiness import build_report
from library_pipeline import AssetRef, transition_intake
from library_source_integrity import payload_tree_sha256
from swift_adapter import CONTRACT, SCHEMA as BRIDGE_SCHEMA
from swift_probe import TOOLCHAIN_PROFILE, read

REPO = "pilialvu75-hue/AI-Orchestrator-Module-Library"
WORKFLOW = ".github/workflows/verify-upstream-swift.yml"
RUN_ID = re.compile(r"\d{5,18}\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")
TEST_SCHEMA = "ai-orchestrator.library-test-report.v1"


class TestPromotionError(ValueError):
    pass


def _github_json(path: str) -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token or len(token) > 8192:
        raise TestPromotionError("trusted GitHub Actions read token unavailable")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "Aivexus-Independent-Swift-CI-Verifier",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise TestPromotionError("GitHub Actions API failed closed") from exc
    if not isinstance(data, dict):
        raise TestPromotionError("invalid GitHub Actions response")
    return data


def verify_run(run_id: str, job_name: str) -> bool:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise TestPromotionError("unsafe GitHub run identifier")
    run = _github_json(f"/actions/runs/{run_id}")
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "push"
        or run.get("head_branch") != "main"
        or run.get("path") != WORKFLOW
        or not SHA40.fullmatch(str(run.get("head_sha") or ""))
        or (run.get("repository") or {}).get("full_name") != REPO
    ):
        raise TestPromotionError(f"unverified protected main workflow run: {run_id}")
    jobs = _github_json(f"/actions/runs/{run_id}/jobs?per_page=100")
    rows = [
        j for j in jobs.get("jobs", [])
        if isinstance(j, dict) and j.get("name") == job_name
    ]
    if len(rows) != 1 or rows[0].get("conclusion") != "success":
        raise TestPromotionError(f"required native job not independently successful: {job_name}")
    if rows[0].get("status") != "completed":
        raise TestPromotionError("native job has not completed")
    return True


def _template_digest(root: Path) -> str:
    template = root / "tools/swift_adapters/diagnostics.logging.v1"
    if not template.is_dir() or template.is_symlink():
        raise TestPromotionError("canonical adapter template missing")
    return payload_tree_sha256(template)


def _eligible(root: Path, path: Path) -> tuple[dict, dict, dict] | None:
    base = path.parent
    if base.is_symlink() or base.parent.is_symlink():
        return None
    if not ID.fullmatch(base.parent.name) or not VERSION.fullmatch(base.name):
        return None
    manifest = read(path)
    upstream = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    if (manifest.get("id") != base.parent.name
            or manifest.get("version") != base.name
            or manifest.get("status") not in {"discovered", "quarantined", "normalized"}
            or payload.get("type") != "upstream_reference"
            or "swift" not in manifest.get("languages", [])
            or "macos" not in manifest.get("platforms", [])
            or CONTRACT not in [
                obj.get("contract_id") for obj in
                ((manifest.get("connector") or {}).get("provides") or [])
                if isinstance(obj, dict)
            ]
            or not isinstance(upstream.get("source_commit"), str)
            or not SHA40.fullmatch(upstream["source_commit"])
            or payload.get("upstream_commit") != upstream["source_commit"]
            or not isinstance(payload.get("sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", payload["sha256"])):
        return None
    swift = base / "provenance/swift-probe.json"
    bridge = base / "provenance/swift-adapter.json"
    if not swift.is_file() or not bridge.is_file():
        return None
    original, adapter = read(swift), read(bridge)
    for proof in (original, adapter):
        if (proof.get("result") != "passed"
                or proof.get("source_commit") != upstream["source_commit"]
                or proof.get("payload_sha256") != payload["sha256"]
                or proof.get("toolchain_profile") != TOOLCHAIN_PROFILE
                or proof.get("certification_authorized") is not False):
            raise TestPromotionError("missing or mismatched native CI attestation")
    if (adapter.get("schema") != BRIDGE_SCHEMA
            or adapter.get("contract_id") != CONTRACT
            or adapter.get("platform") != "macos"
            or adapter.get("adapter_sha256") != _template_digest(root)
            or adapter.get("independent_security_reviewed") is not False
            or original.get("schema") != "ai-orchestrator.library-swift-probe.v1"
            or original.get("platform") != "macos"):
        raise TestPromotionError("native test evidence does not match canonical bridge")
    if payload_tree_sha256(base / "payload") != payload["sha256"]:
        raise TestPromotionError("upstream source changed after native test")
    return manifest, original, adapter


def promote_tested(
    root: Path,
    verify: Callable[[str, str], bool] = verify_run,
    now: str | None = None,
) -> dict:
    for path in sorted((root / "intake").glob("*/*/manifest.json")):
        found = _eligible(root, path)
        if found is None:
            continue
        manifest, original, adapter = found
        # Refuse any unsigned self-reported CI result; check independently
        # against the exact successful job on protected GitHub main.
        if not verify(str(original["github_run_id"]), "verify_untrusted"):
            raise TestPromotionError("upstream GitHub validation was not verified")
        if not verify(str(adapter["github_run_id"]), "verify_adapter_untrusted"):
            raise TestPromotionError("adapter GitHub validation was not verified")
        moment = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        base = path.parent
        report = {
            "schema": TEST_SCHEMA,
            "asset_id": manifest["id"],
            "version": manifest["version"],
            "source_commit": manifest["provenance"]["source_commit"],
            "payload_sha256": manifest["payload"]["sha256"],
            "adapter_sha256": adapter["adapter_sha256"],
            "generated_at": moment,
            "passed": True,
            "validated_on": ["macos"],
            "evidence": {
                "upstream_github_run_id": original["github_run_id"],
                "adapter_github_run_id": adapter["github_run_id"],
                "verification": "two protected-main GitHub jobs independently checked via Actions API",
                "commands": [
                    "swift test --disable-automatic-resolution -j 2",
                    "swift test --disable-automatic-resolution -j 2 --filter AivexusDiagnosticsBridgeTests",
                ],
                "scope_note": "Verified macOS Swift package and Aivexus logging adapter; not iOS, not a full app integration or security approval",
            },
        }
        evidence = base / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "test-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        validation = manifest.setdefault("validation", {})
        validation.setdefault("researcher_recommendation_score", validation.get("score"))
        validation["score"] = 0.95
        validation["score_basis"] = "independently_verified_native_upstream_and_contract_test_jobs"
        validation["tests_passed"] = True
        validation["validated_at"] = moment
        validation["validated_on"] = ["macos"]
        validation["test_report"] = "evidence/test-report.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ref = AssetRef(manifest["id"], manifest["version"])
        while True:
            current = read(path)["status"]
            if current == "tested":
                break
            steps = {"discovered": "quarantined", "quarantined": "normalized",
                     "normalized": "tested"}
            if current not in steps:
                raise TestPromotionError("unexpected source lifecycle")
            transition_intake(root, ref, steps[current])
        verified = read(path)
        verify_manifest_evidence(base, verified)
        if verified["security"].get("reviewed") is True:
            raise TestPromotionError("native job must never approve security review")
        return {
            "tested": 1,
            "asset_id": verified["id"],
            "version": verified["version"],
            "status": verified["status"],
            "security_reviewed": False,
            "certification_authorized": False,
        }
    return {"tested": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.getenv("GITHUB_REPOSITORY", "") != REPO or os.getenv("GITHUB_REF", "") != "refs/heads/main":
        parser.exit(1, "Trusted Swift evidence job must run only on canonical main\n")
    try:
        outcome = promote_tested(args.root)
        if outcome.get("tested"):
            report = build_report(args.root)
            (args.root / "catalog/intake-readiness.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        args.output.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
        print(json.dumps(outcome, sort_keys=True))
        return 0
    except (TestPromotionError, ValueError, OSError) as exc:
        parser.exit(1, f"Trusted Swift evidence rejected: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
