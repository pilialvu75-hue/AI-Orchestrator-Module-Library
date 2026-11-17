"""Stage a genuinely signed independent review for later Library promotion.

The signer/reviewer must be separate from candidate code. This tool never
creates an approval, signature, or trust key. It validates the existing trusted
Ed25519 sign-off before making any changes to intake.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from library_evidence import verify_test_evidence
from library_pipeline import (
    AssetRef, load_json, validate_certification_gates,
    validate_normalization_gates, validate_ref, validate_testing_gates,
)

SBOM_REL = "evidence/independent-sbom.json"
REVIEW_REL = "evidence/independent-security-review.json"


def _input_file(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError(f"{label} must be a nonempty regular file under 1 MiB")
    return path.read_bytes()


def stage(root: Path, asset_id: str, version: str, sbom_path: Path,
          attestation_path: Path, output_root: Path, *, apply: bool = False) -> dict:
    ref = AssetRef(asset_id, version)
    validate_ref(ref)
    root = root.resolve()
    base = root / "intake" / asset_id / version
    if not base.is_dir() or base.is_symlink():
        raise ValueError("tested intake asset is missing or symlinked")
    destination = output_root.resolve() / asset_id / version
    if destination == base or base in destination.parents or destination.exists():
        raise ValueError("staging destination must be separate and unused")
    manifest = load_json(base / "manifest.json")
    if manifest.get("id") != asset_id or manifest.get("version") != version:
        raise ValueError("manifest identity mismatch")
    if manifest.get("status") != "tested" or (manifest.get("security") or {}).get("reviewed") is not False:
        raise ValueError("only unsigned TESTED intake can be staged")
    validate_normalization_gates(manifest, base)
    validate_testing_gates(manifest)
    verify_test_evidence(base, manifest)

    sbom_bytes = _input_file(sbom_path, "SBOM")
    try:
        sbom = json.loads(sbom_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid SBOM JSON") from exc
    if (not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX"
            or not isinstance(sbom.get("components"), list)
            or not sbom["components"]):
        raise ValueError("a populated CycloneDX SBOM is required")
    if asset_id == "utility.int64_arithmetic.external.dartlang.fixnum" and not any(
            isinstance(row, dict) and row.get("purl") == "pkg:pub/fixnum@1.1.1"
            for row in sbom["components"]):
        raise ValueError("reviewed SBOM must contain the exact fixnum 1.1.1 dependency")

    try:
        attestation = json.loads(_input_file(attestation_path, "attestation"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid reviewer attestation JSON") from exc
    if not isinstance(attestation, dict) or not isinstance(attestation.get("statement"), dict):
        raise ValueError("independent signed review statement required")
    statement = attestation["statement"]
    if statement.get("decision") != "APPROVED" or type(statement.get("known_vulnerabilities")) is not int or statement["known_vulnerabilities"] != 0:
        raise ValueError("independent reviewer did not approve a zero-vulnerability candidate")

    security = dict(manifest["security"])
    security.update({
        "reviewed": True, "reviewed_at": statement.get("reviewed_at"),
        "known_vulnerabilities": 0, "sbom": SBOM_REL,
        "review_report": REVIEW_REL,
        "notes": "Exact source/license/SBOM bound to independently signed reviewer approval.",
    })
    manifest["security"] = security
    review = {
        "schema": "ai-orchestrator.library-security-review.v1",
        "asset_id": asset_id, "version": version,
        "source_commit": (manifest.get("provenance") or {}).get("source_commit"),
        "payload_sha256": (manifest.get("payload") or {}).get("sha256"),
        "sbom_sha256": hashlib.sha256(sbom_bytes).hexdigest(),
        "reviewed": True, "reviewed_at": statement.get("reviewed_at"),
        "reviewer_id": statement.get("reviewer_id"),
        "known_vulnerabilities": 0, "decision": "APPROVED",
        "independent_attestation": attestation,
    }
    # The public trust key is read by the pre-existing signature verifier
    # from protected runner configuration. No key from input files is trusted.
    if not os.environ.get("LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM"):
        raise ValueError("protected independent reviewer public key is not configured")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(base, destination, symlinks=False)
        (destination / SBOM_REL).parent.mkdir(parents=True, exist_ok=True)
        (destination / SBOM_REL).write_bytes(sbom_bytes)
        (destination / REVIEW_REL).write_text(
            json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # This checks the real detached signature, exact payload bytes, license,
        # SBOM, CI evidence, and the complete promotion policy.
        validate_certification_gates(manifest, destination)
        if apply:
            for relative in (SBOM_REL, REVIEW_REL):
                target = base / relative
                if target.exists() or target.is_symlink():
                    raise ValueError("refusing to overwrite existing review evidence")
            evidence = base / "evidence"
            evidence.mkdir(parents=True, exist_ok=True)
            for relative in (SBOM_REL, REVIEW_REL):
                shutil.copyfile(destination / relative, base / relative)
            # Commit manifest last: incomplete uploads cannot claim reviewed.
            temp_manifest = base / "manifest.json.signed-review.tmp"
            temp_manifest.write_bytes((destination / "manifest.json").read_bytes())
            temp_manifest.replace(base / "manifest.json")
        return {
            "schema": "aivexus.library.signed-review-stage.v1",
            "asset_id": asset_id, "version": version,
            "status": "SIGNED_REVIEW_STAGED_NOT_CERTIFIED",
            "signature_checked": True,
            "applied_to_intake": apply,
            "promotion_required": True,
        }
    finally:
        # Staging is deliberately ephemeral. Only --apply updates a real intake.
        shutil.rmtree(destination, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--asset-id", default="utility.int64_arithmetic.external.dartlang.fixnum")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Update intake only after verified approval")
    args = parser.parse_args()
    print(json.dumps(stage(args.root, args.asset_id, args.version, args.sbom,
                           args.attestation, args.output_dir, apply=args.apply),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
