"""Verify an independent Ed25519 sign-off before certifying local module source.

The verification key is injected ONLY by the protected main workflow through
a repository-controlled Actions variable; it is never read from a worker
manifest, PR, review JSON or locally authored file.

The signature covers the source tree pin, full license-file bytes, SBOM bytes,
review date, reviewer identity and zero-vulnerability review decision.
Unsigned local JSON claims are not sufficient for automatic certification.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

PUBLIC_KEY_ENV = "LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM"
_ALG = "ed25519-openssl-v1"
_ED25519_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_STATEMENT_FIELDS = {
    "schema", "asset_id", "version", "source_commit", "payload_sha256",
    "sbom_sha256", "license_file_sha256", "reviewed_at", "reviewer_id",
    "known_vulnerabilities", "decision",
}


class ReviewAuthorizationError(ValueError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ReviewAuthorizationError(reason)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _license_file(base: Path, manifest: dict) -> Path:
    raw = (manifest.get("provenance") or {}).get("license_file")
    _require(isinstance(raw, str) and bool(raw.strip()) and "\\" not in raw,
             "independent local review requires an attributable license path")
    parts = raw.split("/")
    _require(not raw.startswith("/") and all(part not in ("", ".", "..") for part in parts),
             "local review license path is unsafe")
    root = base.resolve()
    path = base
    for part in parts:
        path = path / part
        _require(not path.is_symlink(), "independent license evidence cannot follow symlinks")
    _require(path.is_file() and root in path.resolve().parents,
             "independent local review license file missing or escaping")
    _require(0 < path.stat().st_size <= 1024 * 1024,
             "independent local review license evidence empty or oversized")
    return path


def verify_local_review_authorization(base: Path, manifest: dict, report: dict, sbom: Path) -> None:
    """Verify signed reviewer statement against independently configured key.

    This only authenticates a narrowly scoped reviewer assertion. Reviewers
    must examine the actual project license, source, tests, SBOM and risks
    before producing a signature; it is not a vulnerability scanner.
    """
    source = manifest.get("payload") or {}
    payload_type = source.get("type")
    materialized_upstream = (
        payload_type == "upstream_reference"
        and source.get("path") == "payload"
        and isinstance(source.get("sha256"), str)
        and _SHA256.fullmatch(source["sha256"]) is not None
    )
    _require(payload_type == "repository_path" or materialized_upstream,
             "independent review requires a materialized and SHA256-pinned source")
    attestation = report.get("independent_attestation")
    _require(isinstance(attestation, dict)
             and set(attestation) == {"algorithm", "statement", "signature_base64"}
             and attestation.get("algorithm") == _ALG,
             "local code requires independent signed review provenance")
    statement = attestation.get("statement")
    _require(isinstance(statement, dict) and set(statement) == _EXPECTED_STATEMENT_FIELDS,
             "signed security review statement schema mismatch")
    _require(statement.get("schema") == "ai-orchestrator.library-review-authorization.v1"
             and statement.get("decision") == "APPROVED",
             "independent security reviewer has not approved the exact candidate")
    provenance = manifest.get("provenance") or {}
    security = manifest.get("security") or {}
    expected = {
        "asset_id": manifest.get("id"),
        "version": manifest.get("version"),
        "source_commit": provenance.get("source_commit"),
        "payload_sha256": source.get("sha256"),
        "sbom_sha256": _sha256_file(sbom),
        "license_file_sha256": _sha256_file(_license_file(base, manifest)),
        "reviewed_at": security.get("reviewed_at"),
        "known_vulnerabilities": security.get("known_vulnerabilities"),
    }
    for key, value in expected.items():
        _require(statement.get(key) == value,
                 f"independent signed review {key} does not match canonical evidence")
    _require(isinstance(statement.get("source_commit"), str)
             and _SHA40.fullmatch(statement["source_commit"]) is not None,
             "signed review source commit must be immutable")
    for key in ("payload_sha256", "sbom_sha256", "license_file_sha256"):
        _require(isinstance(statement.get(key), str)
                 and _SHA256.fullmatch(statement[key]) is not None,
                 f"signed review {key} must contain full SHA256")
    _require(type(statement.get("known_vulnerabilities")) is int
             and statement["known_vulnerabilities"] == 0,
             "review cannot approve unknown or known vulnerabilities")
    reviewer = statement.get("reviewer_id")
    _require(isinstance(reviewer, str) and 2 <= len(reviewer) <= 128
             and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/-]*", reviewer) is not None,
             "independent reviewer identity must be explicit")
    _require(report.get("reviewer_id") == reviewer
             and report.get("reviewed_at") == statement["reviewed_at"],
             "review report must match signed reviewer and review time")
    _require(report.get("decision") == "APPROVED"
             and report.get("payload_sha256") == source["sha256"],
             "unsigned review metadata contradicts signed approval")
    public_pem = os.environ.get(PUBLIC_KEY_ENV, "")
    _require(isinstance(public_pem, str) and "-----BEGIN PUBLIC KEY-----" in public_pem
             and "-----END PUBLIC KEY-----" in public_pem and len(public_pem) <= 8192,
             "protected independent reviewer public key is not configured")
    encoded = attestation.get("signature_base64")
    _require(isinstance(encoded, str) and len(encoded) <= 256,
             "detached reviewer signature is missing")
    try:
        signature = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ReviewAuthorizationError("detached reviewer signature invalid") from exc
    _require(len(signature) == 64, "detached Ed25519 review signature must be 64 bytes")
    payload = (b"AI-ORCHESTRATOR-LOCAL-REVIEW-v1\n"
               + json.dumps(statement, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True).encode("ascii") + b"\n")
    try:
        with tempfile.TemporaryDirectory(prefix="library-review-") as temp:
            directory = Path(temp)
            key = directory / "reviewer-public.pem"
            message = directory / "signed-review.json"
            signature_file = directory / "signature.bin"
            key.write_text(public_pem, encoding="ascii")
            message.write_bytes(payload)
            signature_file.write_bytes(signature)
            parsed_key = subprocess.run(
                ["openssl", "pkey", "-pubin", "-in", str(key), "-outform", "DER"],
                capture_output=True, timeout=8, check=False,
            )
            _require(parsed_key.returncode == 0
                     and len(parsed_key.stdout) == 44
                     and parsed_key.stdout.startswith(_ED25519_DER_PREFIX),
                     "configured independent reviewer key is not Ed25519")
            verified = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(key),
                 "-rawin", "-in", str(message), "-sigfile", str(signature_file)],
                capture_output=True, timeout=8, check=False,
            )
            _require(verified.returncode == 0,
                     "independent reviewer signature does not authenticate evidence")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewAuthorizationError("independent reviewer signature verification unavailable") from exc
