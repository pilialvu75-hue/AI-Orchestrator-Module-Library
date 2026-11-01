"""Independent-review preflight: evidence readiness, never a security approval."""
import json
from pathlib import Path
from library_review_evidence_crosscheck import verify


def assess(requests, evidence):
    verify(requests, evidence)
    rows = []
    for item, report in zip(requests["requests"], evidence["reports"]):
        reasons = []
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
    args = parser.parse_args()
    result = assess(json.loads(args.requests.read_text()),
                    json.loads(args.evidence.read_text()))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
