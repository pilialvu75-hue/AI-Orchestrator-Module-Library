"""Fast, evidence-checked *sandbox-only* access to real tested Library source.

This is a separate availability tier, never a waiver of production security,
redistribution, or module certification. No reviewer key or manual Main/Reviewer
step is required to assemble a source bundle for an isolated Cantiere test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from library_evidence import EvidenceError, verify_test_evidence
from library_package import (
    PackageError, _files_from_repository_path, _requirements,
    canonical_json, require,
)
from library_pipeline import AssetRef, PipelineError, validate_ref
from library_resolver import sha256_file, tree_sha256

TRUSTED_FIRST_PARTY = "https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library"
INDEX_SCHEMA = "ai-orchestrator.library-experimental-index.v1"
PREVIEW_POLICY = "internal-isolated-evaluation-only"
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def preview_package(root: Path, asset_id: str, version: str) -> dict[str, Any]:
    """Package real, pinned, already tested first-party source without certification.

    This method has no effects on the canonical certified catalog.
    """
    root = root.resolve()
    ref = AssetRef(asset_id, version)
    try:
        validate_ref(ref)
    except PipelineError as exc:
        raise PackageError(str(exc)) from exc
    base = root / "intake" / asset_id / version
    manifest_path = base / "manifest.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(),
            "experimental package requires an existing intake manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackageError("invalid experimental intake manifest") from exc
    require(isinstance(manifest, dict), "experimental manifest must be an object")
    require(manifest.get("id") == asset_id and manifest.get("version") == version,
            "experimental manifest identity mismatch")
    require(manifest.get("status") == "tested",
            "experimental packages require a tested intake candidate")
    require(manifest.get("kind") == "module",
            "only concrete local modules can use experimental packaging")
    provenance = manifest.get("provenance") or {}
    require(provenance.get("origin") == "built_in"
            and provenance.get("source_repository") == TRUSTED_FIRST_PARTY
            and isinstance(provenance.get("source_commit"), str)
            and _SHA40.fullmatch(provenance["source_commit"]) is not None,
            "experimental packaging is restricted to pinned first-party source")
    require(not (manifest.get("dependencies") or []),
            "external dependencies require separate dependency review")
    validation = manifest.get("validation") or {}
    require(validation.get("tests_passed") is True,
            "experimental source requires passing test evidence")
    require(type(validation.get("score")) in (float, int)
            and validation["score"] >= 0.80,
            "experimental source requires score >= 0.80")
    require(isinstance(validation.get("validated_on"), list)
            and bool(validation["validated_on"])
            and set(validation["validated_on"]).issubset(set(manifest.get("platforms") or [])),
            "experimental source requires a bounded tested platform list")
    try:
        verify_test_evidence(base, manifest)
    except EvidenceError as exc:
        raise PackageError(f"unverified tested evidence: {exc}") from exc
    payload = manifest.get("payload") or {}
    require(payload.get("type") == "repository_path",
            "upstream references or absent local source cannot be previewed")
    relative = payload.get("path")
    pinned = payload.get("sha256")
    require(isinstance(relative, str) and bool(relative.strip())
            and isinstance(pinned, str) and _SHA256.fullmatch(pinned) is not None,
            "experimental payload requires pinned source SHA256")
    # The ordinary Library packager independently validates the actual bytes,
    # rejects symlinks, unsafe files, oversized bundles and changed payloads.
    from library_source_integrity import SourceIntegrityError, payload_tree_sha256
    source = base / relative
    require(not source.is_symlink() and source.resolve().is_relative_to(base.resolve()),
            "experimental source path escapes its intake directory")
    try:
        current_digest = payload_tree_sha256(source)
    except (SourceIntegrityError, OSError) as exc:
        raise PackageError(f"experimental source invalid: {exc}") from exc
    require(current_digest == pinned, "experimental source changed after testing")
    files = _files_from_repository_path(base, relative)
    require(files, "no source files available for experimental use")
    report_path = base / validation["test_report"]
    requirements = _requirements(manifest, upstream_reference=False)
    requirements.append({
        "kind": "distributionRestriction",
        "description": "Isolated internal tests only. No production, release, redistribution, or automatic privileged execution; license and security certification pending.",
        "required": True,
    })
    requirements.sort(key=lambda item: (str(item["kind"]), str(item["description"])))
    package = {
        "schema": "ai-orchestrator.library-module-package.v1",
        "asset_id": asset_id,
        "version": version,
        "pin": f"{asset_id}@{version}",
        "tier": "sandbox_preview",
        "status": "tested",
        "certified": False,
        "availability": "experimental",
        "usage_policy": PREVIEW_POLICY,
        "capabilities": sorted(str(v) for v in manifest.get("capabilities") or []),
        "contracts": sorted({
            str(v.get("contract_id")) for v in
            ((manifest.get("connector") or {}).get("provides") or [])
            if isinstance(v, dict) and v.get("contract_id")
        }),
        "targets": sorted(str(v) for v in validation["validated_on"]),
        "files": files,
        "requirements": requirements,
        "integrity": {
            "manifest_sha256": sha256_file(manifest_path),
            "module_tree_sha256": tree_sha256(base),
            "payload_sha256": current_digest,
            "test_report_sha256": sha256_file(report_path),
        },
        "source": {
            "payload_type": "repository_path",
            "source_repository": TRUSTED_FIRST_PARTY,
            "source_commit": provenance["source_commit"],
        },
        "review": {
            "license_verified": False,
            "security_reviewed": False,
            "production_approved": False,
        },
    }
    return {
        "schema": "ai-orchestrator.library-module-package-envelope.v1",
        "package": package,
        "package_sha256": hashlib.sha256(
            canonical_json(package).encode("utf-8")
        ).hexdigest(),
    }


def export_experimental_packages(root: Path) -> dict[str, Any]:
    """Generate a separately labeled index; never add a preview to catalog."""
    root = root.resolve()
    destination = root / "packages"
    entries: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for path in sorted((root / "intake").glob("*/*/manifest.json")):
        asset_id, version = path.parent.parent.name, path.parent.name
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("status") != "tested" or (
                (manifest.get("payload") or {}).get("type") != "repository_path"
            ):
                continue
            envelope = preview_package(root, asset_id, version)
        except (ValueError, KeyError, OSError, PackageError) as exc:
            blocked.append({"pin": f"{asset_id}@{version}", "reason": str(exc)})
            continue
        rel = Path("experimental") / asset_id / version / "package.json"
        file = destination / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        entries.append({
            "pin": f"{asset_id}@{version}",
            "path": f"packages/{rel.as_posix()}",
            "package_sha256": envelope["package_sha256"],
            "tier": "sandbox_preview",
            "production_approved": False,
        })
    report = {
        "schema": INDEX_SCHEMA,
        "policy": PREVIEW_POLICY,
        "certified": False,
        "packages": entries,
        "blocked": blocked,
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "experimental-index.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return {"count": len(entries), "blocked": len(blocked)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sandbox-only verified source previews")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--export", action="store_true")
    parser.add_argument("asset_id", nargs="?")
    parser.add_argument("version", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.export:
            print(json.dumps(export_experimental_packages(args.root), indent=2))
        else:
            require(bool(args.asset_id and args.version), "asset and version required")
            print(json.dumps(
                preview_package(args.root, args.asset_id, args.version), indent=2
            ))
    except (PackageError, OSError) as exc:
        print(f"experimental package unavailable: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
