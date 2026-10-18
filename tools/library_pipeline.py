from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from library_evidence import EvidenceError, verify_manifest_evidence

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
COMMIT_LIKE = re.compile(r"^[A-Fa-f0-9]{7,64}$")
EXTERNAL_ORIGINS = {"researcher", "open_source", "imported"}

INTAKE_TRANSITIONS = {
    "discovered": "quarantined",
    "quarantined": "normalized",
    "normalized": "tested",
}


class PipelineError(Exception):
    pass


@dataclass(frozen=True)
class AssetRef:
    asset_id: str
    version: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PipelineError(f"invalid JSON at {path}: {exc}") from exc


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def asset_dir(root: Path, area: str, ref: AssetRef) -> Path:
    return root / area / ref.asset_id / ref.version


def manifest_path(root: Path, area: str, ref: AssetRef) -> Path:
    return asset_dir(root, area, ref) / "manifest.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineError(message)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_ref(ref: AssetRef) -> None:
    require(ASSET_ID.fullmatch(ref.asset_id) is not None, "asset id must use only letters, digits, dot, underscore or hyphen and cannot contain path separators")
    require(SEMVER.fullmatch(ref.version) is not None, f"invalid semantic version: {ref.version}")


def validate_identity(manifest: dict, ref: AssetRef) -> None:
    require(manifest.get("id") == ref.asset_id, "manifest id does not match intake path")
    require(manifest.get("version") == ref.version, "manifest version does not match intake path")


def validate_no_symlinks(base: Path) -> None:
    require(not base.is_symlink(), "asset directory cannot be a symlink")
    for path in base.rglob("*"):
        require(not path.is_symlink(), f"symlinks are not allowed in untrusted intake: {path.relative_to(base)}")


def validate_external_provenance(manifest: dict, base: Path) -> None:
    provenance = manifest.get("provenance") or {}
    origin = provenance.get("origin")
    require(nonempty(origin), "provenance.origin is required")

    if origin not in EXTERNAL_ORIGINS:
        return

    require(nonempty(provenance.get("source_repository")), "external asset requires provenance.source_repository")
    source_commit = provenance.get("source_commit")
    require(nonempty(source_commit), "external asset requires immutable provenance.source_commit")
    require(COMMIT_LIKE.fullmatch(str(source_commit)) is not None, "external provenance.source_commit must look like an immutable commit SHA")
    require(nonempty(provenance.get("license")), "external asset requires an identified license")

    license_file = provenance.get("license_file")
    require(nonempty(license_file), "external asset requires provenance.license_file")
    resolved = (base / str(license_file)).resolve()
    require(base.resolve() in resolved.parents or resolved == base.resolve(), "license_file must stay inside the asset directory")
    require(resolved.is_file(), f"license file does not exist: {license_file}")


def validate_connector(manifest: dict) -> None:
    connector = manifest.get("connector") or {}
    require(connector.get("standard") == "ai-orchestrator-lego", "connector.standard must be ai-orchestrator-lego")
    require(nonempty(connector.get("standard_version")), "connector.standard_version is required")
    provides = connector.get("provides")
    require(isinstance(provides, list) and provides, "connector.provides must not be empty")

    capabilities = set(manifest.get("capabilities") or [])
    provided_capabilities: set[str] = set()
    for item in provides:
        require(isinstance(item, dict), "connector.provides entries must be objects")
        capability_id = item.get("capability_id")
        contract_id = item.get("contract_id")
        require(nonempty(capability_id), "provided capability_id is required")
        require(nonempty(contract_id), "provided contract_id is required")
        provided_capabilities.add(str(capability_id))

    missing = capabilities - provided_capabilities
    require(not missing, "connector does not provide manifest capabilities: " + ", ".join(sorted(missing)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


MAX_LOCAL_PAYLOAD_FILES = 512
MAX_LOCAL_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_LOCAL_PAYLOAD_FILE_BYTES = 2 * 1024 * 1024


def payload_tree_sha256(source: Path) -> str:
    """Compute a bounded, path-bound digest of actual immutable source bytes.

    Same normalized byte sequence for repository_path payloads and export.
    Symlinks, empty directories and oversized payloads fail before digesting.
    """
    require(source.exists() and not source.is_symlink(),
            "repository_path must point to a real non-symlink payload")
    if source.is_file():
        root, candidates = source.parent, [source]
    else:
        require(source.is_dir(), "repository_path payload must be a file or directory")
        root = source
        candidates = sorted(source.rglob("*"), key=lambda p: p.as_posix())
    require(candidates, "repository_path payload must contain at least one file")
    digest = hashlib.sha256()
    file_count, total = 0, 0
    for item in candidates:
        require(not item.is_symlink(), "repository_path payload may not contain symlinks")
        if item.is_dir():
            continue
        require(item.is_file(), "repository_path contains a non-file entry")
        file_count += 1
        require(file_count <= MAX_LOCAL_PAYLOAD_FILES,
                "repository_path payload exceeds file count limit")
        size = item.stat().st_size
        require(size <= MAX_LOCAL_PAYLOAD_FILE_BYTES,
                "repository_path payload contains an oversized file")
        total += size
        require(total <= MAX_LOCAL_PAYLOAD_BYTES,
                "repository_path payload exceeds total size limit")
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(item)))
    require(file_count > 0, "repository_path payload must contain at least one file")
    return digest.hexdigest()


def validate_payload(manifest: dict, base: Path) -> None:
    payload = manifest.get("payload") or {}
    payload_type = payload.get("type")
    require(payload_type in {"repository_path", "upstream_reference", "archive"}, "invalid payload.type")

    if payload_type == "upstream_reference":
        require(nonempty(payload.get("upstream_repository")), "upstream_reference requires upstream_repository")
        commit = payload.get("upstream_commit")
        require(nonempty(commit), "upstream_reference requires upstream_commit")
        require(COMMIT_LIKE.fullmatch(str(commit)) is not None, "payload.upstream_commit must look like an immutable commit SHA")
        provenance = manifest.get("provenance") or {}
        if provenance.get("source_commit"):
            require(str(provenance["source_commit"]) == str(commit), "payload and provenance commits differ")
        if provenance.get("source_repository"):
            require(str(provenance["source_repository"]).rstrip("/") == str(payload["upstream_repository"]).rstrip("/"), "payload and provenance repositories differ")
        return

    relative = payload.get("path")
    require(nonempty(relative), f"{payload_type} requires payload.path")
    resolved = (base / str(relative)).resolve()
    require(base.resolve() in resolved.parents or resolved == base.resolve(), "payload.path must stay inside the asset directory")
    require(resolved.exists(), f"payload path does not exist: {relative}")

    if payload_type == "repository_path":
        expected = payload.get("sha256")
        require(isinstance(expected, str) and re.fullmatch(r"[0-9a-fA-F]{64}", expected) is not None,
                "repository_path payload requires a SHA256 digest")
        require(payload_tree_sha256(resolved) == expected.lower(),
                "repository_path payload SHA256 mismatch")

    if payload_type == "archive":
        require(resolved.is_file(), "archive payload.path must be a file")
        expected = payload.get("sha256")
        require(nonempty(expected), "archive payload requires sha256")
        require(sha256_file(resolved).lower() == str(expected).lower(), "archive payload sha256 mismatch")


def validate_normalization_gates(manifest: dict, base: Path) -> None:
    validate_no_symlinks(base)
    require(isinstance(manifest.get("capabilities"), list) and manifest["capabilities"], "capabilities must not be empty")
    require(isinstance(manifest.get("platforms"), list) and manifest["platforms"], "platforms must not be empty")
    validate_external_provenance(manifest, base)
    validate_connector(manifest)
    validate_payload(manifest, base)


def validate_testing_gates(manifest: dict) -> None:
    validation = manifest.get("validation") or {}
    require(validation.get("tests_passed") is True, "tested asset requires validation.tests_passed=true")
    try:
        score = float(validation.get("score", 0))
    except (TypeError, ValueError) as exc:
        raise PipelineError("validation.score must be numeric") from exc
    require(score >= 0.80, "tested asset requires validation.score >= 0.80")
    require(nonempty(validation.get("validated_at")), "tested asset requires validation.validated_at")
    validated_on = validation.get("validated_on")
    require(isinstance(validated_on, list) and validated_on, "tested asset requires validation.validated_on")


def validate_evidence_gates(manifest: dict, base: Path) -> None:
    try:
        verify_manifest_evidence(base, manifest)
    except EvidenceError as exc:
        raise PipelineError(str(exc)) from exc


def license_requires_explicit_review(license_name: str) -> bool:
    normalized = license_name.upper().strip()
    if "AGPL" in normalized or "SSPL" in normalized:
        return True
    return re.search(r"(^|[ (|])GPL-[0-9]", normalized) is not None


def validate_certification_gates(manifest: dict, base: Path) -> None:
    validate_normalization_gates(manifest, base)
    validate_testing_gates(manifest)
    validate_evidence_gates(manifest, base)

    security = manifest.get("security") or {}
    require(security.get("reviewed") is True, "certification requires security.reviewed=true")
    require(nonempty(security.get("reviewed_at")), "certification requires security.reviewed_at")
    known = security.get("known_vulnerabilities")
    require(isinstance(known, int) and known >= 0, "security.known_vulnerabilities must be a non-negative integer")
    require(known == 0, "automatic certification is blocked when known vulnerabilities are present")

    license_name = str((manifest.get("provenance") or {}).get("license") or "")
    if license_requires_explicit_review(license_name):
        raise PipelineError("automatic certification is blocked for strong/network copyleft licenses; explicit project-level review is required")


def transition_intake(root: Path, ref: AssetRef, target_status: str) -> dict:
    validate_ref(ref)
    path = manifest_path(root, "intake", ref)
    require(path.is_file(), f"missing intake manifest: {path}")
    manifest = load_json(path)
    validate_identity(manifest, ref)

    current = str(manifest.get("status") or "")
    expected = INTAKE_TRANSITIONS.get(current)
    require(expected is not None, f"status {current!r} cannot be advanced inside intake")
    require(target_status == expected, f"invalid transition {current} -> {target_status}; expected {current} -> {expected}")

    base = path.parent
    if target_status in {"normalized", "tested"}:
        validate_normalization_gates(manifest, base)
    if target_status == "tested":
        validate_testing_gates(manifest)
        validate_evidence_gates(manifest, base)

    manifest["status"] = target_status
    write_json(path, manifest)
    return manifest


def bump_patch(version: str) -> str:
    match = SEMVER.fullmatch(version)
    if match is None:
        raise PipelineError(f"invalid catalog version: {version}")
    major, minor, patch = map(int, match.groups())
    return f"{major}.{minor}.{patch + 1}"


def catalog_entry(manifest: dict, ref: AssetRef) -> dict:
    provides = (manifest.get("connector") or {}).get("provides") or []
    return {
        "id": ref.asset_id,
        "version": ref.version,
        "manifest": f"modules/{ref.asset_id}/{ref.version}/manifest.json",
        "status": "certified",
        "kind": manifest.get("kind"),
        "capabilities": list(manifest.get("capabilities") or []),
        "platforms": list(manifest.get("platforms") or []),
        "contracts": sorted({str(item.get("contract_id")) for item in provides if item.get("contract_id")}),
    }


def already_promoted(root: Path, ref: AssetRef, catalog: dict) -> bool:
    destination = manifest_path(root, "modules", ref)
    if not destination.is_file():
        return False
    manifest = load_json(destination)
    if manifest.get("id") != ref.asset_id or manifest.get("version") != ref.version or manifest.get("status") != "certified":
        return False
    return any(item.get("id") == ref.asset_id and item.get("version") == ref.version and item.get("status") == "certified" for item in catalog.get("assets", []))


def promote(root: Path, ref: AssetRef, *, dry_run: bool = False) -> dict:
    validate_ref(ref)
    catalog_path = root / "catalog" / "index.json"
    catalog = load_json(catalog_path)

    if already_promoted(root, ref, catalog):
        return {"result": "already_promoted", "asset": f"{ref.asset_id}@{ref.version}"}

    source = asset_dir(root, "intake", ref)
    source_manifest_path = source / "manifest.json"
    require(source_manifest_path.is_file(), f"missing intake manifest: {source_manifest_path}")
    manifest = load_json(source_manifest_path)
    validate_identity(manifest, ref)
    require(manifest.get("status") == "tested", "only tested intake assets can be promoted")
    validate_certification_gates(manifest, source)

    destination = asset_dir(root, "modules", ref)
    require(not destination.exists(), f"destination already exists without a matching certified catalog entry: {destination}")
    require(not any(item.get("id") == ref.asset_id and item.get("version") == ref.version for item in catalog.get("assets", [])), "catalog already contains this immutable asset version")

    entry = catalog_entry(manifest, ref)
    if dry_run:
        return {"result": "dry_run_ok", "asset": f"{ref.asset_id}@{ref.version}", "catalog_entry": entry}

    old_catalog_bytes = catalog_path.read_bytes()
    copied = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        copied = True

        promoted_manifest_path = destination / "manifest.json"
        promoted_manifest = load_json(promoted_manifest_path)
        promoted_manifest["status"] = "certified"
        write_json(promoted_manifest_path, promoted_manifest)

        catalog.setdefault("assets", []).append(entry)
        catalog["assets"] = sorted(catalog["assets"], key=lambda item: (str(item.get("id")), str(item.get("version"))))
        catalog["catalog_version"] = bump_patch(str(catalog.get("catalog_version", "0.0.0")))
        catalog["updated_at"] = utc_now()
        write_json(catalog_path, catalog)

        shutil.rmtree(source)
    except Exception:
        if copied and destination.exists():
            shutil.rmtree(destination)
        catalog_path.write_bytes(old_catalog_bytes)
        raise

    return {"result": "promoted", "asset": f"{ref.asset_id}@{ref.version}", "catalog_entry": entry}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="AI Orchestrator Module Library intake/promotion pipeline")
    result.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = result.add_subparsers(dest="command", required=True)

    advance = sub.add_parser("advance", help="advance an intake asset by exactly one lifecycle state")
    advance.add_argument("asset_id")
    advance.add_argument("version")
    advance.add_argument("target", choices=["quarantined", "normalized", "tested"])

    promote_parser = sub.add_parser("promote", help="promote a tested intake asset to certified modules/catalog")
    promote_parser.add_argument("asset_id")
    promote_parser.add_argument("version")
    promote_parser.add_argument("--dry-run", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    ref = AssetRef(args.asset_id, args.version)
    try:
        if args.command == "advance":
            manifest = transition_intake(root, ref, args.target)
            print(json.dumps({"result": "advanced", "asset": f"{ref.asset_id}@{ref.version}", "status": manifest["status"]}, indent=2))
        else:
            print(json.dumps(promote(root, ref, dry_run=args.dry_run), indent=2))
    except PipelineError as exc:
        print(f"LIBRARY PIPELINE FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
