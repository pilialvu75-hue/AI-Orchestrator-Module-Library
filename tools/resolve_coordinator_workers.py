"""Resolve coordinator claim proposals to authorized worker identities.

Only canonical enabled lane_worker actors with explicit 'claim' capability
are eligible. This module does not write inbox requests or impersonate actors.
"""
import argparse
import json
from pathlib import Path


def resolve(root, proposals):
    root = Path(root)
    registry = json.loads((root / ".airlab/control-plane/automation-registry.json").read_text(encoding="utf-8"))
    actors = {}
    for entry in registry.get("automations", []):
        if entry.get("enabled") is True and entry.get("kind") == "lane_worker" and "claim" in entry.get("allowed_operations", []) and "control_plane_mutation" in entry.get("write_capabilities", []) and entry.get("target_lane_policy") == "owner_lane_only":
            lane = entry.get("owner_lane")
            if lane in actors:
                raise ValueError("multiple authorized workers for lane " + lane)
            actors[lane] = entry["actor_id"]
    ready, deferred = [], []
    for proposal in proposals.get("requests", []):
        lane = proposal["lane_id"]
        if lane not in actors:
            deferred.append({"request_id": proposal["request_id"], "reason": "no_authorized_worker"})
            continue
        ready.append({"request_id": proposal["request_id"], "lane_id": lane,
                      "authorized_actor_id": actors[lane],
                      "status": "READY_FOR_ACTOR_SUBMISSION"})
    return {"ready": ready, "deferred": deferred, "submitted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = resolve(args.root, json.loads(args.proposals.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
