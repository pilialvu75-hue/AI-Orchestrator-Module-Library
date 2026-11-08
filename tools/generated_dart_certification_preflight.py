#!/usr/bin/env python3
"""Read-only certification readiness check for the first generated Dart bundle.

Never changes status, signs a review, or claims security approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ASSET_ID = "aivexus.dart.running_total"
VERSION = "0.1.0"
CONTRACT = "math.running_total.v1"


def inspect(bundle_path: Path, sha_path: Path) -> dict:
    raw = bundle_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    expected = sha_path.read_text(encoding="utf-8").strip()
    if actual != expected:
        raise ValueError("bundle SHA256 mismatch")
    bundle = json.loads(raw)
    manifest = bundle.get("manifest") or {}
    connector = manifest.get("connector") or {}
    provides = connector.get("provides") or []
    if (bundle.get("pin") != f"{ASSET_ID}@{VERSION}"
            or manifest.get("id") != ASSET_ID
            or manifest.get("version") != VERSION
            or not any(isinstance(p, dict) and p.get("contract_id") == CONTRACT
                       and p.get("capability_id") == "math.running_total"
                       for p in provides)):
        raise ValueError("generated bundle identity or contract mismatch")
    blockers = []
    provenance = manifest.get("provenance") or {}
    security = manifest.get("security") or {}
    validation = manifest.get("validation") or {}
    if not provenance.get("license") or not provenance.get("license_file"):
        blockers.append("ATTRIBUTABLE_LICENSE_EVIDENCE_MISSING")
    if not validation.get("tests_passed") or not validation.get("test_report"):
        blockers.append("TEST_EVIDENCE_MISSING")
    if not security.get("reviewed") or not security.get("review_report"):
        blockers.append("INDEPENDENT_SIGNED_SECURITY_REVIEW_MISSING")
    if (manifest.get("payload") or {}).get("type") == "archive":
        blockers.append("MATERIALIZED_SOURCE_BOUND_REVIEW_REQUIRED")
    return {
        "schema": "aivexus.running-total-certification-preflight.v1",
        "asset_id": ASSET_ID,
        "version": VERSION,
        "bundle_sha256": actual,
        "ready_for_certification": not blockers,
        "blockers": blockers,
        "note": "Read-only triage, not a certification decision. Protected certification gates remain authoritative.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--sha256-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.bundle, args.sha256_file), indent=2))


if __name__ == "__main__":
    main()
