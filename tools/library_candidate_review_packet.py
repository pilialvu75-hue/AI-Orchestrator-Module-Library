"""Create a focused, fail-closed reviewer checklist for a real candidate.

This is a handoff document, never an independent security approval.
"""
import json
from pathlib import Path


def packet(requests, preflight, asset_id):
    if requests.get("schema") != "aivexus.library.autonomous-public-dart-review-collection.v1":
        raise ValueError("invalid review collection")
    if preflight.get("schema") != "aivexus.library.independent-review-preflight.v1":
        raise ValueError("invalid preflight")
    candidates = [x for x in requests.get("requests", []) if x.get("asset_id") == asset_id]
    gates = [x for x in preflight.get("items", []) if x.get("asset_id") == asset_id]
    if len(candidates) != 1 or len(gates) != 1:
        raise ValueError("candidate and gate must match uniquely")
    candidate, gate = candidates[0], gates[0]
    if gate.get("decision") != "BLOCKED" or gate.get("certification_authorized") is not False:
        raise ValueError("unsigned preflight cannot authorize")
    if candidate.get("certification_authorized") is not False or candidate.get("security_reviewed") is not False:
        raise ValueError("unreviewed candidate must not claim approval")
    source = candidate["source"]
    return {
        "schema": "aivexus.library.reviewer-handoff.v1",
        "asset_id": asset_id,
        "source_repository": source["repository"],
        "source_commit": source["commit"],
        "source_sha256": source["payload_tree_sha256"],
        "license_sha256": source["license_sha256"],
        "tested_ci_run_id": candidate["tested_evidence"]["ci_run_id"],
        "tested_ci_head_sha": candidate["tested_evidence"]["ci_head_sha"],
        "open_blockers": gate["reasons"],
        "reviewer_actions_required": [
            "Independently inspect exact upstream source, adapter and license attribution",
            "Verify dependency inventory, current advisories and security findings",
            "Assess privacy, network, storage and logging behavior",
            "Confirm tested Linux evidence and scope of independent consumer",
            "Use protected reviewer signing key and shared transactional replay ledger",
        ],
        "decision": "BLOCKED",
        "certification_authorized": False,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = packet(json.loads(args.requests.read_text()),
                    json.loads(args.preflight.read_text()), args.asset_id)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
