"""Reproducible, source-bound *technical* review of the TESTED fixnum candidate.

This is an independently executable evidence assessment, not a security
approval. GitHub/Sigstore may attest this report but that must NEVER be
interpreted as permission to certify or install the candidate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from autonomous_public_dart_review import review as rebuild_request
from library_independent_dart_static_audit import audit as rebuild_audit
from library_independent_review_preflight import assess as rebuild_preflight
from library_review_evidence_crosscheck import verify as verify_crosscheck

ASSET = "utility.int64_arithmetic.external.dartlang.fixnum"
VERSION = "0.1.0"
SOURCE_SHA = "b7241fcdfca77f7ec525da0279fa527ff9ca403ca7af592cc9bff804d4776f6a"
SOURCE_COMMIT = "17d1b2cd13991f3cf844886db1c7ad18910a8908"
UPSTREAM_LICENSE_SHA = "ff0b91d4f3c32b25cb6ec84985e8da89b0ba2a2b2f7eef353cda5e5423a20390"
PACKAGE = "pkg:pub/fixnum@1.1.1"
EXPECTED_BLOCKERS = {
    "INDEPENDENT_SOURCE_LICENSE_PRIVACY_REVIEW_REQUIRED",
    "PROTECTED_REVIEWER_SIGNATURE_REQUIRED",
}
MAX_SCAN_AGE = dt.timedelta(hours=1)


def _one(rows, key, asset_id=ASSET):
    matches = [row for row in rows if isinstance(row, dict) and row.get(key) == asset_id]
    if len(matches) != 1:
        raise ValueError("missing or duplicate fixnum evidence identity")
    return matches[0]


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("OSV scan timestamp missing")
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("malformed OSV scan timestamp") from exc
    if result.utcoffset() is None:
        raise ValueError("OSV scan timestamp must include UTC offset")
    return result.astimezone(dt.timezone.utc)


def assess(root, requests, evidence, static, preflight, ci, *, now=None):
    """Check real pinned source, current scans, actual CI identity and policy.

    The verified CI receipt must be fetched in the workflow from GitHub's API
    at runtime, not from a file submitted by the candidate.
    """
    root = Path(root)
    now = dt.datetime.now(dt.timezone.utc) if now is None else now
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError("aware current time required")
    if requests.get("schema") != "aivexus.library.autonomous-public-dart-review-collection.v1":
        raise ValueError("invalid request collection")
    verify_crosscheck(requests, evidence)
    expected_preflight = rebuild_preflight(requests, evidence, static)
    if expected_preflight != preflight:
        raise ValueError("preflight differs from independently recomputed evidence")
    request = _one(requests["requests"], "asset_id")
    report = _one(evidence["reports"], "asset_id")
    audit = _one(static["items"], "asset_id")
    gate = _one(preflight["items"], "asset_id")
    if request != rebuild_request(root, "fixnum"):
        raise ValueError("request does not match the pinned physical source")
    if audit != rebuild_audit(root, request):
        raise ValueError("static audit does not match actual source bytes")
    if (request["version"] != VERSION
            or request["source"]["commit"] != SOURCE_COMMIT
            or request["source"]["payload_tree_sha256"] != SOURCE_SHA
            or request["source"]["license_sha256"] != UPSTREAM_LICENSE_SHA
            or request["tested_evidence"]["verified_on"] != ["linux"]):
        raise ValueError("fixnum version, source or Linux evidence pin changed")
    if (audit["findings"] or audit["static_scan_completed"] is not True
            or gate["decision"] != "BLOCKED"
            or set(gate["reasons"]) != EXPECTED_BLOCKERS
            or gate["certification_authorized"] is not False):
        raise ValueError("unresolved technical finding or malformed review gate")
    if (report["provider"] != "OSV" or report["advisory_scan_completed"] is not True
            or report["vulnerabilities_found"] != 0
            or len(report["packages"]) != 1
            or report["packages"][0]["purl"] != PACKAGE
            or report["packages"][0]["vulnerability_ids"] != []):
        raise ValueError("current OSV evidence is missing or has advisories")
    scanned = _utc(report.get("scanned_at_utc"))
    age = now.astimezone(dt.timezone.utc) - scanned
    if not dt.timedelta(0) <= age <= MAX_SCAN_AGE:
        raise ValueError("OSV evidence is stale or from the future")
    if not isinstance(ci, dict) or (
        ci.get("id") != request["tested_evidence"]["ci_run_id"]
        or ci.get("head_sha") != request["tested_evidence"]["ci_head_sha"]
        or ci.get("name") != "Library isolated verification of Researcher public Dart intake"
        or ci.get("conclusion") != "success"
        or ci.get("status") != "completed"
        or ci.get("event") != "pull_request"
    ):
        raise ValueError("real GitHub CI API receipt does not match tested source")
    base = root / "intake" / ASSET / VERSION
    license_record = (base / "provenance" / "LICENSE").read_bytes()
    original_license = (base / "payload/src/vendor/fixnum/LICENSE").read_bytes()
    if (not original_license or original_license != license_record
            or _digest(original_license) != UPSTREAM_LICENSE_SHA
            or b"Redistribution and use in source and binary forms" not in original_license):
        raise ValueError("original BSD license evidence mismatch")
    sbom = request["dependency_inventory"]["cyclonedx_sbom"]
    expected_purls = {PACKAGE, "pkg:generic/aivexus_external_fixnum@0.1.0"}
    actual_purls = {row.get("purl") or row.get("bom-ref") for row in sbom["components"]}
    if actual_purls != expected_purls or len(sbom["components"]) != 2:
        raise ValueError("unreviewed package in source-bound SBOM")
    return {
        "schema": "aivexus.library.fixnum-technical-review.v1",
        "asset_id": ASSET, "version": VERSION,
        "source_commit": SOURCE_COMMIT, "source_sha256": SOURCE_SHA,
        "license_sha256": UPSTREAM_LICENSE_SHA,
        "sbom_sha256": _digest(json.dumps(sbom, sort_keys=True, separators=(",", ":")).encode()),
        "osv_scan_at": scanned.isoformat(), "osv_known_advisories": 0,
        "static_findings": 0, "tested_ci_run_id": ci["id"],
        "tested_ci_head_sha": ci["head_sha"],
        "validated_on": ["linux"],
        "technical_evidence_checked": True,
        "status": "TECHNICAL_EVIDENCE_READY_PENDING_INDEPENDENT_REVIEW",
        "open_blockers": sorted(EXPECTED_BLOCKERS),
        "security_reviewed": False,
        "license_approved_by_independent_reviewer": False,
        "certification_authorized": False,
        "production_installable": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    for key in ("requests", "evidence", "static-audit", "preflight", "ci", "output"):
        parser.add_argument("--" + key, required=True, type=Path)
    args = parser.parse_args()
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))
    report = assess(args.root, load(args.requests), load(args.evidence),
                    load(args.static_audit), load(args.preflight), load(args.ci))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "certification_authorized": False}))


if __name__ == "__main__":
    main()
