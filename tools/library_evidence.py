from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from library_source_integrity import SourceIntegrityError, payload_tree_sha256


TEST_REPORT_SCHEMA = "ai-orchestrator.library-test-report.v1"
SECURITY_REPORT_SCHEMA = "ai-orchestrator.library-security-review.v1"


class EvidenceError(Exception):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _safe_file(base: Path, raw: object, label: str) -> Path:
    _require(isinstance(raw, str) and bool(raw.strip()), f"{label} is required")
    relative = Path(str(raw))
    _require(not relative.is_absolute(), f"{label} must be relative to the asset directory")
    resolved = (base / relative).resolve()
    root = base.resolve()
    _require(resolved == root or root in resolved.parents, f"{label} escapes the asset directory")
    _require(resolved.is_file(), f"{label} does not exist: {raw}")
    _require(not resolved.is_symlink(), f"{label} cannot be a symlink")
    _require(resolved.stat().st_size > 0, f"{label} cannot be empty")
    return resolved


def _json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EvidenceError(f"invalid JSON in {label}: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(report: dict, manifest: dict, label: str) -> None:
    _require(report.get("asset_id") == manifest.get("id"), f"{label} asset_id does not match manifest")
    _require(report.get("version") == manifest.get("version"), f"{label} version does not match manifest")
    source_commit = (manifest.get("provenance") or {}).get("source_commit")
    if source_commit:
        _require(report.get("source_commit") == source_commit, f"{label} source_commit does not match manifest provenance")


_SHA256 = re.compile(r"[0-9a-f]{64}\\Z")


def _bind_local_source(base: Path, manifest: dict, report: dict, label: str) -> None:
    """Tie a checked report to the manifest pin AND the real source file bytes.

    An upstream-reference-only asset remains subject to its existing legacy
    provenance policy; these local payload checks are not a shortcut to
    accepting upstream references or granting a security review.
    """
    payload = manifest.get("payload") or {}
    _require(isinstance(payload, dict), f"{label} manifest payload must be an object")
    if payload.get("type") != "repository_path":
        return
    pinned = payload.get("sha256")
    declared = report.get("payload_sha256")
    _require(isinstance(pinned, str) and _SHA256.fullmatch(pinned) is not None,
             f"{label} local source payload requires a valid SHA256 pin")
    _require(isinstance(declared, str) and declared == pinned,
             f"{label} payload_sha256 differs from manifest source pin")
    raw_path = payload.get("path")
    _require(isinstance(raw_path, str) and raw_path and chr(92) not in raw_path,
             f"{label} local source path invalid")
    relative = Path(raw_path)
    _require(not relative.is_absolute() and not any(
        part in ("", ".", "..") for part in raw_path.split("/")
    ), f"{label} local source path escapes asset")
    resolved_base = base.resolve()
    _require(not base.is_symlink(), f"{label} asset base may not be a symlink")
    original_path = base / relative
    # Refuse symlinks in every intermediate segment, not just the final path.
    intermediate = base
    for segment in relative.parts:
        intermediate = intermediate / segment
        _require(not intermediate.is_symlink(),
                 f"{label} local source path may not traverse symlinks")
    source = original_path.resolve()
    _require(source != resolved_base and resolved_base in source.parents,
             f"{label} local source path escapes asset")
    try:
        actual = payload_tree_sha256(source)
    except (SourceIntegrityError, OSError) as exc:
        raise EvidenceError(f"{label} local source cannot be verified: {exc}") from exc
    _require(actual == pinned,
             f"{label} actual local source digest differs from manifest and report")


def verify_test_evidence(base: Path, manifest: dict) -> None:
    validation = manifest.get("validation") or {}
    if validation.get("tests_passed") is not True:
        return

    report_path = _safe_file(base, validation.get("test_report"), "validation.test_report")
    report = _json_object(report_path, "validation.test_report")
    _require(report.get("schema") == TEST_REPORT_SCHEMA, "validation.test_report has unsupported schema")
    _identity(report, manifest, "validation.test_report")
    _require(report.get("passed") is True, "validation.test_report must assert passed=true")
    _bind_local_source(base, manifest, report, "validation.test_report")

    report_targets = report.get("validated_on")
    manifest_targets = validation.get("validated_on")
    _require(isinstance(report_targets, list) and bool(report_targets), "validation.test_report validated_on must not be empty")
    _require(isinstance(manifest_targets, list) and bool(manifest_targets), "validation.validated_on must not be empty")
    _require(sorted(map(str, report_targets)) == sorted(map(str, manifest_targets)), "validation.test_report targets do not match manifest validation.validated_on")
    supported = {str(item) for item in manifest.get("platforms") or []}
    _require(set(map(str, manifest_targets)).issubset(supported), "validation.validated_on contains a platform not declared by the asset")


def verify_security_evidence(base: Path, manifest: dict) -> None:
    security = manifest.get("security") or {}
    if security.get("reviewed") is not True:
        return

    report_path = _safe_file(base, security.get("review_report"), "security.review_report")
    sbom_path = _safe_file(base, security.get("sbom"), "security.sbom")
    report = _json_object(report_path, "security.review_report")
    _require(report.get("schema") == SECURITY_REPORT_SCHEMA, "security.review_report has unsupported schema")
    _identity(report, manifest, "security.review_report")
    _require(report.get("reviewed") is True, "security.review_report must assert reviewed=true")
    _bind_local_source(base, manifest, report, "security.review_report")

    known = security.get("known_vulnerabilities")
    _require(isinstance(known, int) and known >= 0, "security.known_vulnerabilities must be a non-negative integer")
    _require(report.get("known_vulnerabilities") == known, "security.review_report vulnerability count does not match manifest")
    _require(report.get("sbom_sha256") == _sha256(sbom_path), "security.review_report SBOM digest does not match security.sbom")


def verify_manifest_evidence(base: Path, manifest: dict) -> None:
    verify_test_evidence(base, manifest)
    verify_security_evidence(base, manifest)
