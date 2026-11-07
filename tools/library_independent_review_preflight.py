"""Independent-review preflight: evidence readiness, never a security approval."""
import json
from pathlib import Path
from library_review_evidence_crosscheck import verify


def assess(requests, evidence, static_audit=None):
    if static_audit is None:
        raise ValueError('independent static source audit is required')
    if static_audit is not None:
        if not isinstance(static_audit, dict):
            raise ValueError('static source audit must be an object')
        if not isinstance(static_audit.get('items'), list):
            raise ValueError('static source audit items must be a list')
        if (static_audit.get('schema') != 'aivexus.library.static-source-audit.v1'
                or len(static_audit.get('items', [])) != len(requests['requests'])):
            raise ValueError('static source audit does not match review collection')
    if (static_audit.get('security_reviewed') is not False
            or static_audit.get('certification_authorized') is not False):
        raise ValueError('unsigned static audit cannot authorize certification')
    verify(requests, evidence)
    # Require a unique source-bound audit record for every requested asset.
    # Positional comparison alone must not permit duplicated audit identities.
    audit_keys = [
        (row.get('asset_id'), row.get('source_payload_sha256'))
        for row in static_audit['items'] if isinstance(row, dict)
    ]
    if len(audit_keys) != len(set(audit_keys)):
        raise ValueError('duplicate static audit source identity')
    rows = []
    for index, (item, report) in enumerate(zip(requests["requests"], evidence["reports"])):
        reasons = []
        if static_audit is not None:
            scanned = static_audit["items"][index]
            if not isinstance(scanned, dict):
                raise ValueError("static audit item must be an object")
            if (scanned.get("asset_id") != item["asset_id"]
                    or scanned.get("source_payload_sha256") != item["source"]["payload_tree_sha256"]
                    or scanned.get("static_scan_completed") is not True):
                raise ValueError("static audit identity or source hash mismatch")
            if (scanned.get('security_reviewed') is not False
                    or scanned.get('certification_authorized') is not False
                    or scanned.get('manual_security_review_required') is not True):
                raise ValueError('static audit item cannot assert security approval')
            findings = scanned.get("findings")
            if not isinstance(findings, list) or any(not isinstance(finding, dict) for finding in findings):
                raise ValueError("static audit findings must be an explicit list of records")
            if findings:
                reasons.append("STATIC_SOURCE_SECURITY_FINDINGS")
        if report["vulnerabilities_found"]:
            reasons.append("KNOWN_UPSTREAM_ADVISORIES")
        if not item["source"].get("all_file_digests"):
            reasons.append("SOURCE_FILE_INVENTORY_MISSING")
        if not item["source"].get("license_sha256"):
            reasons.append("ORIGINAL_LICENSE_DIGEST_MISSING")
        if not item.get("tested_evidence", {}).get("ci_run_id"):
            reasons.append("REPRODUCIBLE_CI_IDENTITY_MISSING")
        reasons.append("INDEPENDENT_SOURCE_LICENSE_PRIVACY_REVIEW_REQUIRED")
        reasons.append("PROTECTED_REVIEWER_SIGNATURE_REQUIRED")
        rows.append({"asset_id": item["asset_id"], "decision": "BLOCKED",
                     "reasons": reasons, "security_reviewed": False,
                     "certification_authorized": False})
    return {"schema": "aivexus.library.independent-review-preflight.v1",
            "items": rows, "count": len(rows),
            "security_reviewed": False, "certification_authorized": False}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--static-audit", type=Path, required=True)
    args = parser.parse_args()
    result = assess(json.loads(args.requests.read_text()),
                    json.loads(args.evidence.read_text()),
                    json.loads(args.static_audit.read_text()))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
