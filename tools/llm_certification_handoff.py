#!/usr/bin/env python3
"""Source-bound, UNSIGNED independent-review handoff for actual Qwen TESTED modules.

Reads validated source as DATA. It does not execute Dart, decide licensing,
assert zero vulnerabilities, sign, review itself or grant certification.
This is the next usable delivery artifact for an independent reviewer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from library_evidence import verify_test_evidence
from library_pipeline import validate_normalization_gates, validate_testing_gates
from library_source_integrity import payload_tree_sha256

_ASSET = re.compile(r"utility[.]llm_generated[.][a-z][a-z0-9_]{1,60}\Z")
_VERSION = re.compile(r"[0-9]+[.][0-9]+[.][0-9]+\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_IMPORTS = {"dart:core", "dart:math", "dart:collection", "dart:convert"}
_IMPORT_RE = re.compile(r"""(?:import|export|part)\s+['"]([^'"]+)['"]""")


def _require(ok: bool, message: str):
    if not ok:
        raise ValueError(message)


def _json(path: Path) -> dict:
    _require(path.is_file() and not path.is_symlink(), "missing JSON: " + str(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "invalid JSON: " + str(path))
    return value


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_license(base: Path, raw: object):
    if not isinstance(raw, str) or not raw or "\\" in raw:
        return None
    segments = raw.split("/")
    if any(p in ("", ".", "..") for p in segments):
        return None
    path = base
    for segment in segments:
        path = path / segment
        if path.is_symlink():
            return None
    return path if path.is_file() and 0 < path.stat().st_size <= 1024 * 1024 else None


def build(root: Path, asset_id: str, version: str):
    _require(_ASSET.fullmatch(asset_id) is not None, "only tested original LLM modules")
    _require(_VERSION.fullmatch(version) is not None, "unsafe version")
    root = root.resolve()
    base = root / "intake" / asset_id / version
    _require(base.is_dir() and not base.is_symlink(), "TESTED intake candidate missing")
    manifest_file = base / "manifest.json"
    manifest = _json(manifest_file)
    _require(manifest.get("id") == asset_id and manifest.get("version") == version,
             "intake identity mismatch")
    _require(manifest.get("status") == "tested", "only actual TESTED modules")
    _require((manifest.get("security") or {}).get("reviewed") is False,
             "already reviewed; do not replace independent reviewer evidence")
    validate_normalization_gates(manifest, base)
    validate_testing_gates(manifest)
    verify_test_evidence(base, manifest)
    payload = manifest["payload"]
    _require(payload.get("type") == "repository_path" and
             payload.get("path") == "payload/src", "unexpected source materialization")
    source = base / payload["path"]
    digest = payload_tree_sha256(source)
    _require(digest == payload.get("sha256"), "source SHA differs from TESTED pin")
    origin = manifest["provenance"]
    _require(_SHA40.fullmatch(str(origin.get("source_commit", ""))) is not None,
             "untrusted source commit")
    report = _json(base / manifest["validation"]["test_report"])
    _require(report.get("independent_consumer_executed") is True
             and report.get("model", "").startswith("ollama-local/")
             and type(report.get("real_workflow_run")) is int,
             "missing real model and separate Dart consumer evidence")
    index = _json(root / "packages" / "experimental-index.json")
    pin = f"{asset_id}@{version}"
    entries = [v for v in index.get("packages", [])
               if isinstance(v, dict) and v.get("pin") == pin]
    _require(len(entries) == 1 and entries[0].get("tier") == "sandbox_preview"
             and entries[0].get("production_approved") is False,
             "candidate not uniquely available as TESTED sandbox package")

    # Inventory the exact files without trusting model-authored paths or code.
    files = []
    flags = []
    for file in sorted(source.rglob("*")):
        if file.is_symlink():
            raise ValueError("symlink in model source")
        if not file.is_file():
            continue
        relative = file.relative_to(source).as_posix()
        _require(file.stat().st_size <= 100000,
                 "oversized source must not enter review bundle")
        files.append({"path": relative, "size": file.stat().st_size,
                      "sha256": _hash(file)})
        if relative.startswith("lib/") and relative.endswith(".dart"):
            text = file.read_text(encoding="utf-8")
            for imported in _IMPORT_RE.findall(text):
                if imported not in _SAFE_IMPORTS:
                    flags.append("UNREVIEWED_DART_IMPORT:" + imported)
            for name in ("Process.run", "Process.start", "HttpClient(",
                         "DynamicLibrary.", "Isolate.spawn", "File("):
                if name in text:
                    flags.append("SOURCE_SENSITIVE_API:" + name)
    _require(bool(files), "source inventory empty")

    pubspec = (source / "pubspec.yaml").read_text(encoding="utf-8")
    package = re.search(r"(?m)^name:\s*([a-z][a-z0-9_]*)\s*$", pubspec)
    _require(package is not None, "Dart package identity missing")
    # We can only attest to no runtime third-party dependencies if the
    # runtime "dependencies:" section is absent. Never infer a clean advisory
    # scan from a missing package lock or from Dart's test-only dependency.
    declared_runtime = re.search(r"(?m)^dependencies:\s*$", pubspec)
    if declared_runtime is not None:
        flags.append("RUNTIME_DEPENDENCY_INVENTORY_AND_OSV_REQUIRED")
    purl = f"pkg:pub/{package.group(1)}@{version}"
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {
            "type": "library", "bom-ref": purl, "name": package.group(1),
            "version": version, "purl": purl,
        }},
        "components": [{"type": "library", "bom-ref": purl,
                        "name": package.group(1), "version": version, "purl": purl}],
        "dependencies": [{"ref": purl, "dependsOn": [] if declared_runtime is None else []}],
    }
    # The SBOM above is a SOURCE-level inventory for a library with no
    # runtime third-party dependencies. It is NOT a vulnerability scan or a
    # complete inventory of the test runner's dev-dependency lock.
    sbom_bytes = (json.dumps(bom, indent=2, sort_keys=True) + "\n").encode("utf-8")
    license_path = _safe_license(base, origin.get("license_file"))
    declared_license = origin.get("license")
    blockers = ["INDEPENDENT_SIGNED_SECURITY_REVIEW_REQUIRED",
                "LIVE_SECURITY_ADVISORY_REVIEW_NOT_DONE"]
    if not isinstance(declared_license, str) or not declared_license.strip():
        blockers.append("RIGHTS_HOLDER_LICENSE_DECISION_REQUIRED")
    if license_path is None:
        blockers.append("ATTRIBUTABLE_LICENSE_FILE_MISSING")
    if declared_runtime is not None:
        blockers.append("RUNTIME_DEPENDENCIES_NOT_RESOLVED")
    blockers += sorted(set(flags))

    request = {
        "schema": "aivexus.library.llm-certification-request.v1",
        "asset_id": asset_id, "version": version,
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "certification_authorized": False, "security_reviewed": False,
        "independently_signed": False, "production_approved": False,
        "source": {
            "repository": origin.get("source_repository"),
            "commit": origin["source_commit"],
            "payload_sha256": digest,
            "manifest_sha256": _hash(manifest_file),
            "files": files,
        },
        "test_evidence": {
            "report_sha256": _hash(base / manifest["validation"]["test_report"]),
            "model": report["model"], "real_run_id": report["real_workflow_run"],
            "independent_consumer_claim": True,
            "github_run_independently_reverified": False,
            "tested_targets": manifest["validation"]["validated_on"],
        },
        "published_sandbox": entries[0],
        "license": {
            "declared": declared_license,
            "path": origin.get("license_file"),
            "file_sha256": _hash(license_path) if license_path else None,
            "rights_independently_confirmed": False,
        },
        "security": {
            "cyclonedx_sbom_sha256": hashlib.sha256(sbom_bytes).hexdigest(),
            "sbom_scope": "shipped library itself; no runtime dependencies declared"
                          if declared_runtime is None else "INCOMPLETE",
            "runtime_advisory_scan_completed": False,
            "source_static_findings": sorted(set(flags)),
            "independent_reviewer_approval": False,
        },
        "blockers": sorted(set(blockers)),
        "next_step": "Separate authorized reviewer must verify the immutable "
                     "source, legal license, dependency/advisory evidence and "
                     "security risks; only then sign with protected Ed25519 "
                     "identity. Do not self-approve or change status flags.",
    }
    return request, sbom_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    args = parser.parse_args()
    request, bom = build(args.root, args.asset_id, args.version)
    args.request.parent.mkdir(parents=True, exist_ok=True)
    args.sbom.parent.mkdir(parents=True, exist_ok=True)
    args.request.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    args.sbom.write_bytes(bom)
    print(f"Unsigned source review request: {args.asset_id}: {','.join(request['blockers'])}")


if __name__ == "__main__":
    main()
