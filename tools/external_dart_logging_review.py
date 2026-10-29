"""Bounded read-only security preflight and independent-review request.

For the first REAL external Dart module. This inspects exact original upstream
blobs plus a separately developed Aivexus adapter. It NEVER constitutes a
security review, automatically certifies a module or invokes untrusted code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from library_evidence import EvidenceError, verify_test_evidence
from library_source_integrity import SourceIntegrityError, payload_tree_sha256

CANDIDATE = Path("intake/diagnostics.logging.dartlang.logging_adapter/0.1.0")
SANDBOX = Path("sandbox/external_dart_logging")
ASSET = "diagnostics.logging.dartlang.logging_adapter"
COMMIT = "8151b9f57fa3fee10421a19ce24470e143c0dee5"
TREE = "90ba3565cb83facd809fe382826f61904a7489c8"
PAYLOAD = "eacf34e460dd796eae2a9d62f9f0ff75a4946a3d36d7b6b37d5f0b7ba26b3474"
RUN = 40821013224
RUN_SHA = "c6e3b21da9a949e13ae5aecc363060b5c211b5c9"
REPO = "https://github.com/dart-lang/core"
PIN = "pkg:pub/logging@1.3.0"
LOCAL = "pkg:generic/aivexus_external_logging@0.1.0"
SHA40 = re.compile(r"[a-f0-9]{40}\\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\\Z")
IMPORT_RE = re.compile(r"""(?:import|export)\\s+['"]([^'"]+)['"]""")
MAX_FILES = 64


class ExternalReviewError(ValueError):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise ExternalReviewError(reason)


def checked_file(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(),
            f"missing or symlinked evidence file: {path}")
    require(path.stat().st_size <= 1024 * 1024,
            f"oversized evidence file: {path}")
    return path.read_bytes()


def json_file(path: Path) -> dict:
    try:
        obj = json.loads(checked_file(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExternalReviewError(f"invalid evidence JSON: {path}") from exc
    require(isinstance(obj, dict), f"evidence must be a JSON object: {path}")
    return obj


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(source: Path) -> list[dict]:
    files = []
    require(source.is_dir() and not source.is_symlink(), "source directory missing")
    for item in sorted(source.rglob("*"), key=lambda p: p.relative_to(source).as_posix()):
        require(not item.is_symlink(), "source contains a symlink")
        if item.is_dir():
            continue
        data = checked_file(item)
        files.append({
            "path": item.relative_to(source).as_posix(),
            "bytes": len(data),
            "sha256": sha(data),
        })
        require(len(files) <= MAX_FILES, "unbounded source file count")
    require(files, "empty external source")
    return files


def build_request(repo_root: Path) -> dict:
    root = repo_root.resolve()
    base = root / CANDIDATE
    manifest_path = base / "manifest.json"
    manifest = json_file(manifest_path)
    prov = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    validation = manifest.get("validation") or {}
    security = manifest.get("security") or {}

    require(manifest.get("id") == ASSET and manifest.get("version") == "0.1.0",
            "unexpected module identity")
    require(manifest.get("status") == "tested" and security.get("reviewed") is False,
            "preflight is not a substitute for independent authorization")
    require(validation.get("tests_passed") is True
            and validation.get("validated_on") == ["linux"]
            and manifest.get("platforms") == ["linux"],
            "Linux-only real tests are required; no inferred platform claims")
    require(prov.get("origin") == "open_source"
            and prov.get("source_repository") == REPO
            and prov.get("source_commit") == COMMIT
            and prov.get("source_git_tree") == TREE
            and prov.get("source_subtree") == "pkgs/logging",
            "immutable upstream provenance changed")
    require(payload.get("type") == "repository_path"
            and payload.get("path") == "payload/src"
            and payload.get("sha256") == PAYLOAD
            and payload.get("upstream_commit") == COMMIT
            and payload.get("upstream_repository") == REPO,
            "expected combined upstream and adapter SHA256 pin differs")
    source = base / "payload/src"
    try:
        actual = payload_tree_sha256(source)
        verify_test_evidence(base, manifest)
    except (SourceIntegrityError, EvidenceError, OSError) as exc:
        raise ExternalReviewError(f"materialized source or passing tests invalid: {exc}") from exc
    require(actual == PAYLOAD, "materialized source bytes drifted")
    receipt_path = base / "tests/dart-linux-ci-report.json"
    receipt = json_file(receipt_path)
    evidence = receipt.get("evidence") or {}
    require(
        receipt.get("asset_id") == ASSET
        and receipt.get("version") == "0.1.0"
        and receipt.get("payload_sha256") == PAYLOAD
        and receipt.get("passed") is True
        and receipt.get("validated_on") == ["linux"]
        and receipt.get("security_reviewed") is False
        and receipt.get("certification_authorized") is False
        and evidence.get("github_run_id") == RUN
        and evidence.get("github_commit") == RUN_SHA
        and evidence.get("workflow_conclusion") == "success",
        "exact pinned Linux CI test receipt changed"
    )

    sources = inventory(source)
    sandbox = inventory(root / SANDBOX)
    require(sources == sandbox,
            "Library intake must contain exactly the tested external source and adapter")
    original = source / "vendor/logging"
    upstream = json_file(source / "UPSTREAM_PROVENANCE.json")
    require(upstream.get("repository") == REPO
            and upstream.get("source_commit") == COMMIT
            and upstream.get("source_subtree") == "pkgs/logging"
            and upstream.get("source_git_tree_sha") == TREE
            and upstream.get("origin") == "public"
            and upstream.get("license") == "BSD-3-Clause"
            and upstream.get("security_reviewed") is False
            and upstream.get("certification_authorized") is False,
            "upstream manifest claims mismatch or self-certifies")
    blobs = upstream.get("git_blob_sha_by_path")
    require(isinstance(blobs, dict)
            and len(blobs) == upstream.get("upstream_source_file_count") == 13,
            "pinned public upstream inventory incomplete")
    actual_original = {p.relative_to(original).as_posix()
                       for p in original.rglob("*") if p.is_file()}
    require(set(blobs) == actual_original, "original upstream file list changed")
    for relative, git_sha in blobs.items():
        require(isinstance(relative, str) and relative
                and not relative.startswith("/") and "\\\\" not in relative
                and all(s not in {"", ".", ".."} for s in relative.split("/")),
                "unsafe upstream blob path")
        require(isinstance(git_sha, str) and SHA40.fullmatch(git_sha) is not None,
                "upstream blob missing Git SHA")
        contents = checked_file(original / relative)
        actual_git_sha = hashlib.sha1(
            b"blob " + str(len(contents)).encode("ascii") + b"\\x00" + contents
        ).hexdigest()
        require(actual_git_sha == git_sha, f"original upstream Git blob changed: {relative}")

    license_bytes = checked_file(original / "LICENSE")
    require(prov.get("license") == "BSD-3-Clause"
            and prov.get("license_file") == "provenance/LICENSE"
            and checked_file(base / "provenance/LICENSE") == license_bytes,
            "verified original BSD-3-Clause license is missing")
    require(b"Redistribution and use in source and binary forms" in license_bytes,
            "unexpected license content")
    upstream_spec = checked_file(original / "pubspec.yaml").decode("utf-8")
    require(re.search(r"(?m)^name: logging$", upstream_spec) is not None
            and re.search(r"(?m)^version: 1\\.3\\.0$", upstream_spec) is not None
            and "dependencies:" not in upstream_spec,
            "upstream dependencies or pinned package changed")
    adapter_spec = checked_file(source / "pubspec.yaml").decode("utf-8")
    require(re.search(r"(?m)^name: aivexus_external_logging$", adapter_spec) is not None
            and adapter_spec.count("logging:") == 1
            and re.search(r"(?m)^\\s+path: vendor/logging$", adapter_spec) is not None
            and "git:" not in adapter_spec
            and "dependency_overrides:" not in adapter_spec
            and "dev_dependencies:" not in adapter_spec,
            "unexpected adapter dependency; manual review required")
    adapter_src = checked_file(source / "lib/aivexus_external_logging.dart").decode("utf-8")
    imports = sorted(set(IMPORT_RE.findall(adapter_src)))
    require(imports == ["dart:async", "package:logging/logging.dart"],
            "adapter imports changed: review network/process/privacy privileges")

    risks = [
        {
            "id": "INPUT_SYNTAX_IS_NOT_PRIVACY_ALLOWLIST",
            "severity": "blocking",
            "description": (
                "emit(eventCode) accepts any syntactically valid identifier, not only "
                "known static event names. Such identifiers can contain sensitive "
                "labels or identifiers. A strict closed vocabulary and adversarial "
                "tests should be considered before production use."
            ),
            "review_status": "OPEN",
        },
        {
            "id": "UPSTREAM_LOGGER_CAN_CREATE_GLOBAL_STATE_IF_USED_DIRECTLY",
            "severity": "requires_review",
            "description": (
                "The upstream logging package has global/hierarchical logging APIs. "
                "The tested Aivexus adapter uses Logger.detached and verifies root "
                "stream isolation, but other consumers can still import upstream "
                "logging and must not capture raw user content."
            ),
            "review_status": "OPEN",
        },
        {
            "id": "APPLICATION_LIFECYCLE_NOT_INTEGRATED",
            "severity": "requires_review",
            "description": (
                "The module was tested in a separate Dart consumer on Ubuntu only. "
                "Flutter host integration, persistence/transport/privacy policy, "
                "Android runtime and lifecycle are not certified."
            ),
            "review_status": "OPEN",
        },
    ]
    components = [
        {"type": "library", "name": "logging", "version": "1.3.0",
         "purl": PIN, "licenses": [{"license": {"id": "BSD-3-Clause"}}],
         "externalReferences": [{"type": "vcs", "url": REPO + "/tree/" + COMMIT + "/pkgs/logging"}]},
        {"type": "library", "name": "aivexus_external_logging", "version": "0.1.0",
         "bom-ref": LOCAL, "properties": [
             {"name": "aivexus:payload-sha256", "value": PAYLOAD},
             {"name": "aivexus:independent-security-reviewed", "value": "false"},
         ]},
    ]
    components[0]["bom-ref"] = PIN
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {"type": "application",
                     "name": ASSET, "version": "0.1.0"}},
        "components": components,
        "dependencies": [{"ref": LOCAL, "dependsOn": [PIN]},
                         {"ref": PIN, "dependsOn": []}],
    }
    return {
        "schema": "ai-orchestrator.external-logging-security-review-request.v1",
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "candidate": f"{ASSET}@0.1.0",
        "module_status": "tested",
        "source": {"repository": REPO, "commit": COMMIT,
                   "subtree_git_sha": TREE, "combined_payload_sha256": PAYLOAD,
                   "manifest_sha256": sha(checked_file(manifest_path)),
                   "files": sources, "source_file_count": len(sources),
                   "original_upstream_file_count": 13,
                   "original_license_sha256": sha(license_bytes)},
        "functional_test_claims": {
            "runner": "ubuntu-24.04",
            "reported_github_run_id": RUN,
            "reported_github_head_sha": RUN_SHA,
            "receipt_sha256": sha(checked_file(receipt_path)),
            "independently_verified_github_run": False,
            "standalone_consumer_test": "PR #206 passed Ubuntu CI",
            "platforms_verified_by_this_packet": [],
        },
        "dependency_inventory": {
            "source_imports": imports,
            "package_dependencies": [PIN],
            "cyclonedx_sbom": sbom,
            "live_vulnerability_scan_performed": False,
            "known_vulnerabilities_reviewed_by_independent_authority": False,
        },
        "risks_requiring_resolution": risks,
        "independent_review_steps": [
            "Review original BSD-3-Clause terms/attribution and all vendored bytes.",
            "Inspect pinned adapter and upstream logging for privacy and unsafe input propagation.",
            "Fix or explicitly resolve arbitrary event-code privacy leakage before deployment.",
            "Independently check actual CI conclusion and rerun adversarial integration tests.",
            "Independently inspect and scan dependencies; complete license/privacy security review.",
            "Only authorized independent reviewer may sign the exact SHA256-pinned source, SBOM and license statement with protected Ed25519 key.",
            "Retest Android and Flutter host integration before claiming Android runtime support.",
        ],
        "independent_security_reviewed": False,
        "license_approved_by_independent_reviewer": False,
        "reviewer_signature_present": False,
        "production_approved": False,
        "certification_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = build_request(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("Verified immutable external Dart source; independent security review REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
