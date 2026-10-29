from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from library_resolver import asset_record, catalog, safe_repo_path, sha256_file
from library_pipeline import PipelineError, payload_tree_sha256

PACKAGE_SCHEMA = "ai-orchestrator.library-module-package.v1"
PAYLOAD_SCHEMA = "ai-orchestrator.library-intake-payload.v1"
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
FORBIDDEN_SEGMENTS = {".git", ".dart_tool", ".gradle", "build", "node_modules"}
FORBIDDEN_FILES = {".env", "key.properties", "keystore.properties", "local.properties"}
FORBIDDEN_SUFFIXES = {".jks", ".keystore", ".p12", ".pfx", ".pem", ".key"}


class PackageError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _safe_relative(path: str) -> bool:
    if not path or path.startswith(("/", "~")) or "\\" in path or ":" in path or "\x00" in path:
        return False
    segments = path.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        return False
    lower = [segment.lower() for segment in segments]
    if any(segment in FORBIDDEN_SEGMENTS for segment in lower):
        return False
    file_name = lower[-1]
    if file_name in FORBIDDEN_FILES:
        return False
    if any(file_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return False
    return True


def _decode_text(content: bytes, path: str) -> str:
    require(len(content) <= MAX_TEXT_FILE_BYTES, f"reusable file exceeds 2 MiB: {path}")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageError(f"reusable file is not UTF-8 text: {path}") from exc


def _entry(root: Path, asset_id: str, version: str) -> dict[str, Any]:
    matches = [
        item
        for item in catalog(root)["assets"]
        if isinstance(item, dict)
        and item.get("id") == asset_id
        and item.get("version") == version
    ]
    require(len(matches) == 1, f"catalog pin not found or ambiguous: {asset_id}@{version}")
    return matches[0]


def _requirements(manifest: dict[str, Any], *, upstream_reference: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for dependency in manifest.get("dependencies") or []:
        if not isinstance(dependency, dict) or not dependency.get("name"):
            continue
        description = str(dependency["name"])
        if dependency.get("version"):
            description += f" {dependency['version']}"
        if dependency.get("source"):
            description += f" ({dependency['source']})"
        result.append({"kind": "dependency", "description": description, "required": True})

    connector = manifest.get("connector") or {}
    configuration_schema = connector.get("configuration_schema")
    if isinstance(configuration_schema, str) and configuration_schema.strip():
        result.append(
            {
                "kind": "configuration",
                "description": f"Apply configuration schema {configuration_schema.strip()}",
                "required": True,
            }
        )

    for constraint in (manifest.get("integration") or {}).get("known_constraints") or []:
        if isinstance(constraint, str) and constraint.strip():
            result.append(
                {
                    "kind": "manualReview",
                    "description": constraint.strip(),
                    "required": False,
                }
            )

    if upstream_reference:
        payload = manifest.get("payload") or {}
        repository = str(payload.get("upstream_repository") or "").strip()
        commit = str(payload.get("upstream_commit") or "").strip()
        result.append(
            {
                "kind": "manualReview",
                "description": f"Review target integration of included original upstream source {repository}@{commit}; source-only export is not an Aivexus adapter",
                "required": True,
            }
        )

    if upstream_reference and (manifest.get("connector") or {}).get("integration_mode") == "adapter":
        result.append({
            "kind": "manualReview",
            "description": (
                "Aivexus contract adapter is NOT included in the upstream source package; "
                "implement, independently review and test the adapter before application integration"
            ),
            "required": True,
        })
    result.sort(key=lambda item: (str(item["kind"]), str(item["description"]), bool(item["required"])))
    return result


def _files_from_canonical_archive(path: Path, expected_sha: str) -> list[dict[str, str]]:
    require(path.is_file(), f"archive payload does not exist: {path}")
    require(sha256_file(path).lower() == expected_sha.lower(), "archive payload sha256 mismatch")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PackageError(f"archive is not a supported canonical JSON payload: {exc}") from exc
    require(isinstance(payload, dict) and payload.get("schema") == PAYLOAD_SCHEMA, "unsupported archive payload schema")
    entries = payload.get("files")
    require(isinstance(entries, list) and entries, "canonical archive files must not be empty")

    files: list[dict[str, str]] = []
    previous: str | None = None
    seen: set[str] = set()
    for entry in entries:
        require(isinstance(entry, dict), "canonical archive file entry must be an object")
        relative = entry.get("path")
        encoded = entry.get("content_base64")
        require(isinstance(relative, str) and _safe_relative(relative), "unsafe canonical archive path")
        require(relative not in seen, "duplicate canonical archive path")
        if previous is not None:
            require(previous < relative, "canonical archive paths must be strictly sorted")
        seen.add(relative)
        previous = relative
        require(isinstance(encoded, str), f"missing content_base64 for {relative}")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PackageError(f"invalid base64 for {relative}") from exc
        files.append(
            {
                "source_path": relative,
                "target_path": relative,
                "content": _decode_text(raw, relative),
            }
        )
    return files


def _files_from_repository_path(base: Path, relative: str) -> list[dict[str, str]]:
    require(_safe_relative(relative), "unsafe repository payload path")
    source = safe_repo_path(base, relative)
    require(source.exists(), f"repository payload path does not exist: {relative}")
    candidates = [source] if source.is_file() else sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda item: item.as_posix(),
    )
    require(candidates, "repository payload contains no files")

    result: list[dict[str, str]] = []
    root = source.parent if source.is_file() else source
    for path in candidates:
        require(not path.is_symlink(), f"symlinks are not packageable: {path}")
        target = path.relative_to(root).as_posix()
        require(_safe_relative(target), f"unsafe repository payload file: {target}")
        result.append(
            {
                "source_path": path.relative_to(base).as_posix(),
                "target_path": target,
                "content": _decode_text(path.read_bytes(), target),
            }
        )
    return result


def build_package(root: Path, asset_id: str, version: str, *, include_deprecated: bool = False) -> dict[str, Any]:
    root = root.resolve()
    entry = _entry(root, asset_id, version)
    record = asset_record(root, entry)
    require(record.get("status") == "certified", "only certified assets can be exported")
    availability = str(record.get("availability") or "active")
    require(availability != "revoked", "revoked assets can never be exported")
    if availability == "deprecated":
        require(include_deprecated, "deprecated asset export requires explicit opt-in")
    require(availability in {"active", "deprecated"}, f"unsupported availability: {availability}")

    manifest_path = safe_repo_path(root, str(record["paths"]["manifest"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    payload = manifest.get("payload") or {}
    payload_type = payload.get("type")
    files: list[dict[str, str]]
    upstream_reference = payload_type == "upstream_reference"

    if payload_type == "archive":
        relative = str(payload.get("path") or "").strip()
        expected_sha = str(payload.get("sha256") or "").strip().lower()
        require(relative and expected_sha, "archive payload requires path and sha256")
        files = _files_from_canonical_archive(safe_repo_path(base, relative), expected_sha)
    elif payload_type == "repository_path":
        relative = str(payload.get("path") or "").strip()
        expected = str(payload.get("sha256") or "").strip().lower()
        require(relative, "repository_path payload requires path")
        require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
                "repository_path payload requires SHA256")
        source = safe_repo_path(base, relative)
        try:
            actual = payload_tree_sha256(source)
        except PipelineError as exc:
            raise PackageError(str(exc)) from exc
        require(actual == expected, "repository_path payload SHA256 mismatch")
        files = _files_from_repository_path(base, relative)
    elif payload_type == "upstream_reference":
        repository = str(payload.get("upstream_repository") or "").strip()
        commit = str(payload.get("upstream_commit") or "").strip()
        require(repository and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
                "upstream_reference requires repository and immutable full commit SHA")
        expected = payload.get("sha256")
        require(payload.get("path") == "payload"
                and isinstance(expected, str)
                and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
                "certified upstream source must be materialized at payload with a SHA256 pin; "
                "metadata-only references are not exportable")
        provenance = manifest.get("provenance") or {}
        require(provenance.get("source_commit") == commit
                and str(provenance.get("source_repository") or "").rstrip("/") == repository.rstrip("/"),
                "upstream_reference repository/commit provenance mismatch")
        source = safe_repo_path(base, "payload")
        require(source.is_dir() and not source.is_symlink(),
                "materialized upstream source must be a real directory")
        try:
            actual = payload_tree_sha256(source)
        except PipelineError as exc:
            raise PackageError(str(exc)) from exc
        require(actual == expected, "upstream_reference payload SHA256 mismatch")
        # Export only the original source bytes pinned for independent review.
        # Do NOT blend in an unsigned Aivexus adapter from another directory.
        files = _files_from_repository_path(base, "payload")
    else:
        raise PackageError(f"unsupported payload.type: {payload_type}")

    provides = (manifest.get("connector") or {}).get("provides") or []
    contracts = sorted(
        {
            str(item.get("contract_id"))
            for item in provides
            if isinstance(item, dict) and item.get("contract_id")
        }
    )
    package = {
        "schema": PACKAGE_SCHEMA,
        "asset_id": asset_id,
        "version": version,
        "pin": f"{asset_id}@{version}",
        "availability": availability,
        "capabilities": sorted(str(value) for value in manifest.get("capabilities") or []),
        "contracts": contracts,
        "targets": sorted(str(value) for value in manifest.get("platforms") or []),
        "files": files,
        "requirements": _requirements(manifest, upstream_reference=upstream_reference),
        "integrity": {
            "manifest_sha256": record["integrity"]["manifest_sha256"],
            "module_tree_sha256": record["integrity"]["module_tree_sha256"],
        },
        "source": {
            "payload_type": payload_type,
            "upstream_repository": payload.get("upstream_repository"),
            "upstream_commit": payload.get("upstream_commit"),
            "verified_payload_sha256": payload.get("sha256") if upstream_reference else None,
            "adapter_included": False if upstream_reference else None,
        },
    }
    package_json = canonical_json(package)
    return {
        "schema": "ai-orchestrator.library-module-package-envelope.v1",
        "package": package,
        "package_sha256": hashlib.sha256(package_json.encode("utf-8")).hexdigest(),
    }


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export one exact certified Module Library package")
    parser.add_argument("asset_id")
    parser.add_argument("version")
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--include-deprecated", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        envelope = build_package(
            args.root,
            args.asset_id,
            args.version,
            include_deprecated=args.include_deprecated,
        )
    except PackageError as exc:
        print(f"package error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
