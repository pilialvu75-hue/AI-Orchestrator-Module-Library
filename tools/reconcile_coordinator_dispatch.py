"""Read-only dispatch receipts: reconcile proposals against canonical claim state.

A proposal is not execution. Only an actual canonical claim with the matching
work item proves acceptance; otherwise the task remains awaiting an actor.
"""
import argparse
import json
from pathlib import Path


def reconcile(root, proposals):
    root = Path(root)
    canonical = json.loads((root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
    states = {}
    for relative in canonical.get("workstreams", []):
        state = json.loads((root / relative).read_text(encoding="utf-8"))
        states[state["id"]] = state
    receipts = []
    for request in proposals.get("requests", []):
        lane = states[request["lane_id"]]
        claim = lane.get("active_claim") or {}
        expected = request["payload"]["work_item"]
        if claim.get("work_item") == expected:
            status = "CLAIM_OBSERVED"
        elif claim:
            status = "CONFLICT_OTHER_CLAIM"
        elif lane.get("status") != "READY":
            status = "LANE_NOT_READY"
        elif lane.get("state_version") != request["expected_state_version"]:
            status = "STALE_VERSION"
        else:
            status = "AWAITING_ACTOR_SUBMISSION"
        receipts.append({"request_id": request["request_id"],
                         "lane_id": request["lane_id"], "status": status,
                         "canonical_state_version": lane["state_version"]})
    return {"receipts": receipts, "mutated": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reconcile(args.root, json.loads(args.proposals.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
