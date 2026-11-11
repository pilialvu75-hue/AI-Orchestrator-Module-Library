"""Fail-closed certification decision gate; does not issue or verify signatures.

Only an independently verified attestation may be passed in by a future
protected reviewer job. This module deliberately never publishes packages.
"""
import json
from pathlib import Path


def decide(preflight, attestation=None):
    if not isinstance(preflight, dict) or preflight.get("schema") != "aivexus.library.independent-review-preflight.v1":
        raise ValueError("invalid independent review preflight")
    rows = preflight.get("items")
    if not isinstance(rows, list) or not rows or preflight.get("count") != len(rows):
        raise ValueError("missing or inconsistent review items")
    if len({r.get("asset_id") for r in rows if isinstance(r, dict)}) != len(rows):
        raise ValueError("duplicate or malformed review identities")
    if attestation is not None and not isinstance(attestation, dict):
        raise ValueError("attestation must be an object")
    results = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("asset_id"), str) or not row["asset_id"]:
            raise ValueError("malformed review item")
        reasons = row.get("reasons")
        if row.get("decision") != "BLOCKED" or not isinstance(reasons, list) or not reasons:
            raise ValueError("preflight must remain fail-closed")
        # This job is intentionally incapable of independently validating a
        # protected reviewer signature. Never trust a caller-supplied boolean
        # or an unverified signature field as an authorization.
        results.append({"asset_id": row["asset_id"], "decision": "BLOCKED",
                        "reasons": sorted(set(reasons + ["VERIFIED_INDEPENDENT_ATTESTATION_UNAVAILABLE"])),
                        "certification_authorized": False})
    return {"schema": "aivexus.library.certification-decision.v1",
            "items": results, "count": len(results),
            "certification_authorized": False}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = decide(json.loads(args.preflight.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
