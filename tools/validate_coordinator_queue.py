"""Validate proposed coordinator tasks against the canonical lane's real scope.

A READY lane does not imply an arbitrary task may be claimed. Repositories,
explicit scope, and unresolved current next_action must be surfaced before
automatic dispatch can be safely enabled.
"""
import argparse
import json
from pathlib import Path


def validate(root, queue):
    root = Path(root)
    canonical = json.loads((root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
    lanes = {}
    for relative in canonical.get("workstreams", []):
        lane = json.loads((root / relative).read_text(encoding="utf-8"))
        lanes[lane["id"]] = lane
    findings = []
    for task in queue.get("tasks", []):
        lane = lanes.get(task.get("lane"))
        reasons = []
        if not lane:
            reasons.append("unknown_lane")
        else:
            if lane.get("role") != "worker" or lane.get("activation") != "active":
                reasons.append("inactive_or_nonworker_lane")
            if lane.get("status") != "READY" or lane.get("active_claim"):
                reasons.append("lane_unavailable")
            if lane.get("next_action") and not task.get("acknowledges_next_action"):
                reasons.append("unreconciled_lane_next_action")
        if not task.get("repository") or not task.get("scope"):
            reasons.append("missing_bounded_scope")
        findings.append({"task": task.get("id"), "lane": task.get("lane"),
                         "eligible": not reasons, "reasons": reasons})
    return {"findings": findings, "all_eligible": all(x["eligible"] for x in findings),
            "mutated": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = validate(a.root, json.loads(a.queue.read_text(encoding="utf-8")))
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
