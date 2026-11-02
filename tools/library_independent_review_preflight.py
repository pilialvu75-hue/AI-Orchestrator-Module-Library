"""Independent-review preflight: evidence readiness, never a security approval."""
import json
from pathlib import Path
from library_review_evidence_crosscheck import verify


def assess(requests, evidence, static_audit=None):
    if static_audit is not None:
        if (static_audit.get('schema') != 'aivexus.library.static-source-audit.v1'
                or len(static_audit.get('items', [])) != len(requests['requests'])):
            raise ValueError('static source audit does not match review collection')
    verify(requests, evidence)
    rows = []
    for index, (item, report) in enumerate(zip(requests["requests"], evidence["reports"])):
        reasons = []
        if static_audit is not None:
            scanned = static_audit["items"][index]
            if (scanned.get("asset_id") != item["asset_id"]
                    or scanned.get("source_payload_sha256") != item["source"]["payload_tree_sha256"]
                    or scanned.get("static_scan_completed") is not True):
                raise ValueError("static audit identity or source hash mismatch")
            if scanned.get("findings"):
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
    parser.add_argument("--static-audit", type=Path)
    args = parser.parse_args()
    result = assess(json.loads(args.requests.read_text()),
                    json.loads(args.evidence.read_text()),
                    json.loads(args.static_audit.read_text()) if args.static_audit else None)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
