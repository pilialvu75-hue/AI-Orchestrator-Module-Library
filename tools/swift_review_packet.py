"""Read-only, source-bound independent review request for tested Swift bridge.

Never approves code, changes a manifest, executes upstream, or signs anything.
An OSV preflight or protected CI job result is not an independent privacy audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from swift_sandbox_bundle import SandboxBundleError, select
from swift_probe import read

SCHEMA = "ai-orchestrator.swift-independent-review-request.v1"
CANDIDATE = Path("intake/diagnostics.logging.avdlee.diagnostics/0.1.0")
REQUIRED_FINDINGS = frozenset({
    "global_stdout_stderr_capture",
    "process_environment_access",
    "system_metrics_monitoring",
})


class SwiftReviewPacketError(ValueError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise SwiftReviewPacketError(reason)


def _bytes(path: Path) -> bytes:
    _require(path.is_file() and not path.is_symlink(),
             f"review evidence missing or symlinked: {path.name}")
    _require(path.stat().st_size <= 1024 * 1024,
             f"review evidence exceeds bounded size: {path.name}")
    return path.read_bytes()


def _hash(path: Path) -> str:
    return hashlib.sha256(_bytes(path)).hexdigest()


def build_review_packet(root: Path) -> dict:
    root = root.resolve()
    try:
        selection = select(root)
    except (SandboxBundleError, ValueError, OSError) as exc:
        raise SwiftReviewPacketError("source, native CI or preflight verification failed") from exc
    _require(selection.get("count") == 1, "no eligible tested Swift source for independent review")
    base = root / CANDIDATE
    manifest = read(base / "manifest.json")
    _require(
        manifest.get("id") == selection["asset_id"]
        and manifest.get("version") == selection["version"]
        and manifest.get("status") == "tested"
        and (manifest.get("security") or {}).get("reviewed") is False,
        "candidate identity or unreviewed status changed"
    )

    preflight_file = base / "evidence/security-preflight.json"
    preflight = read(preflight_file)
    adapter_file = base / "provenance/swift-adapter.json"
    adapter = read(adapter_file)
    test_file = base / "evidence/test-report.json"
    test_receipt = read(test_file)
    sbom_file = base / "evidence/sbom.cdx.json"
    provenance_license = base / "provenance/LICENSE"
    upstream_license = base / "payload/LICENSE"

    _require(
        _bytes(provenance_license) == _bytes(upstream_license),
        "review license bytes differ from audited upstream source"
    )
    _require(
        preflight.get("sbom_sha256") == _hash(sbom_file) == selection["sbom_sha256"],
        "SBOM was changed after source-bound security preflight"
    )
    _require(
        adapter.get("adapter_sha256") == selection["adapter_sha256"]
        and test_receipt.get("adapter_sha256") == selection["adapter_sha256"],
        "bridge template does not match previously tested bridge"
    )
    privacy_findings = preflight.get("source_privacy_findings")
    _require(isinstance(privacy_findings, list) and privacy_findings,
             "source privacy risk findings absent")
    rules = {item.get("rule") for item in privacy_findings if isinstance(item, dict)}
    _require(REQUIRED_FINDINGS.issubset(rules), "critical process capture risks missing")
    for item in privacy_findings:
        _require(isinstance(item, dict) and item.get("classification")
                 == "requires_independent_privacy_security_review",
                 "source privacy classification incorrectly weakened")
        name = item.get("source_path")
        _require(isinstance(name, str) and name and ".." not in Path(name).parts
                 and not Path(name).is_absolute(),
                 "source risk path is unsafe")
        _require((base / "payload" / name).is_file()
                 and not (base / "payload" / name).is_symlink(),
                 "risk source reference is missing")

    _require(preflight.get("reviewed") is False
             and preflight.get("certification_authorized") is False
             and adapter.get("independent_security_reviewed") is False
             and adapter.get("certification_authorized") is False,
             "review request must not convert a scan to certification")
    return {
        "schema": SCHEMA,
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "asset_id": selection["asset_id"],
        "version": selection["version"],
        "source": {
            "repository": (manifest.get("provenance") or {}).get("source_repository"),
            "commit": selection["source_commit"],
            "payload_tree_sha256": selection["payload_sha256"],
            "manifest_sha256": _hash(base / "manifest.json"),
            "original_license_sha256": _hash(upstream_license),
            "license_evidence_sha256": _hash(provenance_license),
        },
        "tested_adapter": {
            "contract_id": selection["contract_id"],
            "template_tree_sha256": selection["adapter_sha256"],
            "platform_tested": ["macos"],
            "upstream_test_run_id": selection["upstream_github_run_id"],
            "adapter_test_run_id": selection["adapter_github_run_id"],
            "adapter_receipt_sha256": _hash(adapter_file),
            "test_report_sha256": _hash(test_file),
            "independently_verify_github_jobs": True,
            "adapter_risks": [
                "initialize(allowProcessWideLogCapture=true) starts process-wide capture; this is not an end-user consent dialog",
                "redaction covers only known token/password patterns passed through log(); arbitrary PII and captured stdout/stderr are not fully redacted",
                "adapter source is a separate overlay and is not part of the original upstream source tree hash",
            ],
        },
        "security_evidence": {
            "sbom_sha256": selection["sbom_sha256"],
            "preflight_sha256": _hash(preflight_file),
            "dependency_licenses": preflight.get("dependency_licenses"),
            "osv_vulnerability_ids_reported": preflight.get("osv_vulnerability_ids"),
            "osv_queries_reported": preflight.get("osv_queries"),
            "static_source_privacy_findings": privacy_findings,
            "scope": preflight.get("security_scope"),
            "vulnerabilities_absent_proven": False,
        },
        "independent_review_checklist": [
            "Audit process-wide stdout/stderr redirection, control of activation and stopping, environment/metrics access and privacy impact",
            "Assess explicit end-user consent, data retention, deletion, support-export and transport boundaries",
            "Assess all captured messages for tokens, personal data and non-bridge logging paths; bridge regex redaction is not a general privacy solution",
            "Validate source, adapter, license, dependency SBOM and GitHub CI job outcomes by independently checking each pinned byte/hash",
            "Confirm Swift/macOS-only target and retest any changed bridge or upstream source before integration",
            "Approve or reject via an independently controlled Ed25519 signed statement bound to exact source, license, SBOM and reviewer identity",
        ],
        "reviewer_signature_present": False,
        "security_reviewed": False,
        "license_verified_by_reviewer": False,
        "production_approved": False,
        "certification_authorized": False,
        "platforms_not_verified": ["android", "windows", "linux", "web", "ios"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = build_review_packet(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print("Independent Swift review REQUEST only; no security approval or certification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
