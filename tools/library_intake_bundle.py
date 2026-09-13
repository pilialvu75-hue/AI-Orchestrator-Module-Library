from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from library_pipeline import AssetRef, PipelineError, validate_ref

BUNDLE_SCHEMA = "ai-orchestrator.library-intake-bundle.v1"
PAYLOAD_SCHEMA = "ai-orchestrator.library-intake-payload.v1"
SHA256 = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN_SEGMENTS = {".git", ".dart_tool", "build", "node_modules"}
FORBIDDEN_FILES = {".env", "key.properties", "keystore.properties", "local.properties"}
FORBIDDEN_SUFFIXES = {".jks", ".keystore", ".p12", ".pfx", ".pem", ".key"}


class IntakeBundleError(Exception):
    pass


@dataclass(frozen=True)
class VerifiedIntakeBundle:
    ref: AssetRef
    manifest_path: str
    payload_path: str
    manifest: dict[str, Any]
    payload_json: str
    payload_sha256: str
    bundle_sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntakeBundleError(message)


def _safe_relative_path(value: str) -> bool:
    if not value or value.startswith(("/", "~")) or "\\" in value or ":" in value or "\x00" in value:
        return False
    segments = value.split("/")
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


def _parse_pin(pin: object) -> AssetRef:
    _require(isinstance(pin, str) and "@" in pin, "bundle pin must be asset@version")
    asset_id, version = str(pin).rsplit("@", 1)
    ref = AssetRef(asset_id, version)
    try:
        validate_ref(ref)
    except PipelineError as exc:
        raise IntakeBundleError(str(exc)) from exc
    return ref


def _validate_payload_json(payload_json: str) -> None:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise IntakeBundleError(f"invalid payload_json: {exc}") from exc
    _require(isinstance(payload, dict), "payload_json must decode to an object")
    _require(payload.get("schema") == PAYLOAD_SCHEMA, "unsupported payload schema")
    files = payload.get("files")
    _require(isinstance(files, list) and files, "payload files must not be empty")

    seen: set[str] = set()
    previous_path: str | None = None
    for entry in files:
        _require(isinstance(entry, dict), "payload file entries must be objects")
        path = entry.get("path")
        encoded = entry.get("content_base64")
        _require(isinstance(path, str) and _safe_relative_path(path), "unsafe payload file path")
        _require(path not in seen, "duplicate payload file path")
        if previous_path is not None:
            _require(previous_path < path, "payload file paths must be strictly sorted")
        seen.add(path)
        previous_path = path
        _require(isinstance(encoded, str), "payload file content_base64 is required")
        try:
            base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise IntakeBundleError(f"invalid base64 payload for {path}") from exc


def verify_bundle_bytes(raw: bytes, expected_bundle_sha256: str) -> VerifiedIntakeBundle:
    expected = expected_bundle_sha256.strip().lower()
    _require(SHA256.fullmatch(expected) is not None, "expected bundle sha256 must be 64 lowercase hex characters")
    actual_bundle_sha256 = _sha256_bytes(raw)
    _require(actual_bundle_sha256 == expected, "bundle sha256 mismatch")

    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntakeBundleError(f"invalid bundle JSON: {exc}") from exc
    _require(isinstance(bundle, dict), "bundle must be a JSON object")
    _require(bundle.get("schema") == BUNDLE_SCHEMA, "unsupported intake bundle schema")

    ref = _parse_pin(bundle.get("pin"))
    expected_manifest_path = f"intake/{ref.asset_id}/{ref.version}/manifest.json"
    manifest_path = bundle.get("manifest_path")
    _require(manifest_path == expected_manifest_path, "bundle manifest_path does not match pin")

    payload_path = bundle.get("payload_path")
    _require(isinstance(payload_path, str), "bundle payload_path is required")
    _require(payload_path.startswith("payload/"), "bundle payload_path must stay below payload/")
    _require(_safe_relative_path(payload_path), "unsafe bundle payload_path")

    payload_sha256 = bundle.get("payload_sha256")
    _require(isinstance(payload_sha256, str), "bundle payload_sha256 is required")
    payload_sha256 = payload_sha256.lower()
    _require(SHA256.fullmatch(payload_sha256) is not None, "invalid bundle payload_sha256")

    payload_json = bundle.get("payload_json")
    _require(isinstance(payload_json, str), "bundle payload_json is required")
    _require(
        _sha256_bytes(payload_json.encode("utf-8")) == payload_sha256,
        "canonical payload sha256 mismatch",
    )
    _validate_payload_json(payload_json)

    manifest = bundle.get("manifest")
    _require(isinstance(manifest, dict), "bundle manifest is required")
    _require(manifest.get("id") == ref.asset_id, "manifest id does not match pin")
    _require(manifest.get("version") == ref.version, "manifest version does not match pin")
    _require(manifest.get("status") == "discovered", "incoming manifest status must be discovered")

    descriptor = manifest.get("payload")
    _require(isinstance(descriptor, dict), "manifest payload descriptor is required")
    _require(descriptor.get("type") == "archive", "bundle v1 requires manifest payload.type=archive")
    _require(descriptor.get("path") == payload_path, "manifest and bundle payload paths differ")
    manifest_payload_sha = str(descriptor.get("sha256") or "").lower()
    _require(manifest_payload_sha == payload_sha256, "manifest and bundle payload digests differ")

    return VerifiedIntakeBundle(
        ref=ref,
        manifest_path=manifest_path,
        payload_path=payload_path,
        manifest=manifest,
        payload_json=payload_json,
        payload_sha256=payload_sha256,
        bundle_sha256=actual_bundle_sha256,
    )


def verify_bundle_file(path: Path, expected_bundle_sha256: str) -> VerifiedIntakeBundle:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IntakeBundleError(f"cannot read bundle: {path}: {exc}") from exc
    return verify_bundle_bytes(raw, expected_bundle_sha256)


def _matches_existing(destination: Path, bundle: VerifiedIntakeBundle) -> bool:
    manifest_file = destination / "manifest.json"
    payload_file = destination / bundle.payload_path
    if not manifest_file.is_file() or not payload_file.is_file():
        return False
    try:
        existing_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        existing_payload = payload_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return existing_manifest == bundle.manifest and existing_payload == bundle.payload_json


def materialize_bundle(root: Path, bundle: VerifiedIntakeBundle) -> Path:
    root = root.resolve()
    intake_root = root / "intake"
    parent = intake_root / bundle.ref.asset_id
    destination = parent / bundle.ref.version
    parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        _require(destination.is_dir(), "intake destination exists and is not a directory")
        if _matches_existing(destination, bundle):
            return destination
        raise IntakeBundleError("intake destination already exists with divergent content")

    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle.ref.version}.incoming-", dir=parent))
    try:
        manifest_file = temporary / "manifest.json"
        manifest_file.write_text(
            json.dumps(bundle.manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        payload_file = temporary / bundle.payload_path
        payload_file.parent.mkdir(parents=True, exist_ok=True)
        payload_file.write_text(bundle.payload_json, encoding="utf-8")

        _require(
            _sha256_bytes(payload_file.read_bytes()) == bundle.payload_sha256,
            "materialized payload sha256 mismatch",
        )
        if destination.exists():
            if _matches_existing(destination, bundle):
                return destination
            raise IntakeBundleError("intake destination appeared with divergent content")
        temporary.rename(destination)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify/materialize AI Orchestrator Library intake bundles")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("verify", "materialize"):
        command = subparsers.add_parser(name)
        command.add_argument("bundle", type=Path)
        command.add_argument("--expected-sha256", required=True)
        if name == "materialize":
            command.add_argument("--root", type=Path, default=_default_root())

    args = parser.parse_args(argv)
    try:
        bundle = verify_bundle_file(args.bundle, args.expected_sha256)
        if args.command == "verify":
            print(f"verified {bundle.ref.asset_id}@{bundle.ref.version} {bundle.bundle_sha256}")
            return 0
        destination = materialize_bundle(args.root, bundle)
        print(destination)
        return 0
    except IntakeBundleError as exc:
        print(f"intake bundle error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
