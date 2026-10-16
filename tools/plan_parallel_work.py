"""Deterministic, non-mutating assignment planner for independent AI Orchestrator work.

Input JSON:
  tasks: [{id, lane, depends_on: [], status: "READY", proposal_requires_owner: false}]
  lanes: [{id, busy: false}]
  completed: [task ids]
  max_parallel: positive integer

Output is a proposal only: actual claims must still use the canonical inbox.
No approval, merge, certification, or canonical-state mutation occurs here.
"""
import argparse
import json
from pathlib import Path


def plan(payload):
    tasks = payload.get("tasks", [])
    lanes = payload.get("lanes", [])
    completed = set(payload.get("completed", []))
    limit = payload.get("max_parallel", len(lanes))
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("max_parallel must be a nonnegative integer")
    lane_ids = [lane["id"] for lane in lanes]
    if len(lane_ids) != len(set(lane_ids)):
        raise ValueError("duplicate lane id")
    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task id")
    known = set(ids) | completed
    for task in tasks:
        if any(dep not in known for dep in task.get("depends_on", [])):
            raise ValueError("unknown dependency for " + task["id"])
    available = {lane["id"] for lane in lanes if not lane.get("busy", False)}
    assignments, deferred = [], []
    for task in tasks:
        tid, lane = task["id"], task["lane"]
        if task.get("status", "READY") != "READY":
            deferred.append({"task": tid, "reason": "not_ready"})
        elif task.get("proposal_requires_owner", False):
            deferred.append({"task": tid, "reason": "owner_decision_required"})
        elif not set(task.get("depends_on", [])).issubset(completed):
            deferred.append({"task": tid, "reason": "dependencies_pending"})
        elif lane not in available:
            deferred.append({"task": tid, "reason": "lane_unavailable"})
        elif len(assignments) >= limit:
            deferred.append({"task": tid, "reason": "parallel_limit"})
        else:
            assignments.append({"task": tid, "lane": lane, "action": "request_canonical_claim"})
            available.remove(lane)
    return {"assignments": assignments, "deferred": deferred, "state_mutated": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(json.dumps(plan(json.loads(args.input.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
