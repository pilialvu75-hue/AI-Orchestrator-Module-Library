"""Offline, unprivileged evidence inventory for the first real Dart Library candidate.

Generates a source-pinned CycloneDX SBOM and a bounded import/dependency
inventory, NOT a vulnerability scanner or an independent security review.
No manifest lifecycle fields or security.reviewed flag are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from library_source_integrity import SourceIntegrityError, payload_tree_sha256

ASSET_ID = "diagnostics.logging.library.privacy_events"
VERSION = "0.1.0"
CANDIDATE = Path("intake") / ASSET_ID / VERSION
MAX_FILES = 512
_SHA256 = re.compile(r"[a-f0-9]{64}")
_PACKAGE = re.compile(r"[a-z][a-z0-9_]*")
_IMPORT = re.compile(r"""^\s*(?:import|export)\s+['"]([^'"]+)['"]""", re.MULTILINE)


class PreflightError(ValueError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise PreflightError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def security_preflight(repo_root: Path) -> dict:
    candidate = repo_root / CANDIDATE
    manifest_file = candidate / "manifest.json"
    require(manifest_file.is_file() and not manifest_file.is_symlink(),
            "candidate manifest missing or symlinked")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "candidate manifest is not an object")
    require(manifest.get("id") == ASSET_ID and manifest.get("version") == VERSION,
            "candidate ID/version changed")
    require(manifest.get("status") in {"discovered", "quarantined", "normalized", "tested"},
            "preflight cannot attest certified status")
    require((manifest.get("security") or {}).get("reviewed") is False,
            "security-review decision must be owned by an independent reviewer")
    payload = manifest.get("payload") or {}
    require(isinstance(payload, dict)
            and payload.get("type") == "repository_path"
            and payload.get("path") == "payload/src",
            "unexpected source payload location/type")
    declared = payload.get("sha256")
    require(isinstance(declared, str) and _SHA256.fullmatch(declared) is not None,
            "candidate is not pinned to a full source digest")
    source = candidate / "payload/src"
    try:
        actual = payload_tree_sha256(source)
    except (SourceIntegrityError, OSError) as exc:
        raise PreflightError(f"candidate source integrity failed: {exc}") from exc
    require(actual == declared, "source digest differs from immutable candidate pin")

    pubspec_path = source / "pubspec.yaml"
    require(pubspec_path.is_file() and not pubspec_path.is_symlink(),
            "candidate pubspec.yaml missing or symlinked")
    pubspec = pubspec_path.read_text(encoding="utf-8")
    name = re.search(r"^name:\s*([a-z][a-z0-9_]*)\s*$", pubspec, re.MULTILINE)
    version = re.search(r"^version:\s*(\S+)\s*$", pubspec, re.MULTILINE)
    require(name is not None and _PACKAGE.fullmatch(name.group(1)) is not None
            and name.group(1) == "privacy_diagnostic_events",
            "unexpected Dart package name")
    require(version is not None and version.group(1) == VERSION,
            "unexpected Dart package version")
    for dependency_key in ("dependencies", "dev_dependencies", "dependency_overrides"):
        occurrences = re.findall(
            rf"^{dependency_key}:\s*([^\n]*)$", pubspec, re.MULTILINE
        )
        require(len(occurrences) <= 1,
                f"duplicate {dependency_key} declarations must be investigated")
        # Deliberately narrow: this first candidate is dependency-free. Any
        # future dependency requires a new lockfile/SBOM and updated policy.
        require(not occurrences or occurrences[0].strip() == "{}",
                f"{dependency_key} is not empty; independent dependency review required")
    require("git:" not in pubspec and "path:" not in pubspec,
            "unreviewed Git/path dependencies are not allowed")

    paths: list[dict] = []
    for entry in sorted(source.rglob("*"), key=lambda p: p.as_posix()):
        require(not entry.is_symlink(), "source tree may not contain symlinks")
        if entry.is_dir():
            continue
        require(entry.is_file(), "source tree contains a special file")
        relative = entry.relative_to(source).as_posix()
        paths.append({
            "path": relative, "bytes": entry.stat().st_size,
            "sha256": sha256_file(entry),
        })
        require(len(paths) <= MAX_FILES, "candidate file count exceeds limit")
        if entry.suffix == ".dart":
            # This is a deterministic import inventory, not a proof that no
            # unsafe runtime behavior exists in the source.
            code = entry.read_text(encoding="utf-8")
            for imported in _IMPORT.findall(code):
                require(imported.startswith("package:privacy_diagnostic_events/")
                        or imported == "dart:core",
                        f"unreviewed Dart import requires independent inspection: {imported}")
    require(paths, "candidate source tree is empty")
    test_file = candidate / "tests/dart-linux-ci-report.json"
    test_report_sha256 = sha256_file(test_file) if test_file.is_file() else None
    tested = (manifest.get("validation") or {}).get("tests_passed") is True
    if tested:
        require(test_report_sha256 is not None, "tested candidate missing CI test report")
        report = json.loads(test_file.read_text(encoding="utf-8"))
        require(isinstance(report, dict)
                and report.get("asset_id") == ASSET_ID
                and report.get("payload_sha256") == declared
                and report.get("passed") is True,
                "existing test report not bound to candidate source")
    return {
        "schema": "ai-orchestrator.library-local-security-preflight.v1",
        "asset_id": ASSET_ID,
        "version": VERSION,
        "candidate_status": manifest["status"],
        "payload_tree_sha256": declared,
        "test_report_sha256": test_report_sha256,
        "source_files": paths,
        "third_party_pub_dependencies": [],
        "dart_imports_policy": "only_self_package_and_dart_core_in_pinned_source",
        "sbom": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "library",
                    "name": "privacy_diagnostic_events",
                    "version": VERSION,
                    "purl": "pkg:pub/privacy_diagnostic_events@0.1.0",
                },
            },
            "components": [],
            "dependencies": [{
                "ref": "pkg:pub/privacy_diagnostic_events@0.1.0",
                "dependsOn": [],
            }],
        },
        "security_reviewed": False,
        "security_certified": False,
        "license_verified": False,
        "vulnerability_scanned": False,
        "runtime_validated": False,
        "note": (
            "Read-only source inventory, dependency declaration inspection "
            "and SBOM; not an independent security review or vulnerability scan."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = security_preflight(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Read-only candidate preflight generated; security_reviewed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
