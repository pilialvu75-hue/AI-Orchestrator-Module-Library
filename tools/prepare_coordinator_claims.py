"""Prepare claim requests for explicit approval/submission by authorized lane actors.

This is deliberately not an inbox writer: automation cannot impersonate worker
identities or silently acquire claims. Canonical inbox validates identity and
expected_state_version when the authorized actor submits each request.
"""
import argparse
import json
from pathlib import Path


def prepare(root, plan, queue):
    root = Path(root)
    by_id = {task["id"]: task for task in queue.get("tasks", [])}
    canonical = json.loads((root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
    states = {}
    for relative in canonical.get("workstreams", []):
        state = json.loads((root / relative).read_text(encoding="utf-8"))
        states[state["id"]] = state
    requests = []
    for assignment in plan.get("assignments", []):
        task = by_id[assignment["task"]]
        lane = states[assignment["lane"]]
        if lane.get("status") != "READY" or lane.get("active_claim") is not None:
            raise ValueError("lane became unavailable; regenerate plan")
        for field in ("repository", "scope"):
            if not task.get(field):
                raise ValueError("task requires " + field)
        requests.append({
            "schema_version": 1,
            "request_id": "coordinator-" + str(queue["revision"]) + "-" + task["id"],
            "lane_id": lane["id"],
            "operation": "claim",
            "expected_state_version": lane["state_version"],
            "payload": {
                "work_item": task["id"],
                "repository": task["repository"],
                "scope": task["scope"],
            },
            "submission_status": "AWAITING_AUTHORIZED_ACTOR",
        })
    return {"requests": requests, "submitted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.root,
                     json.loads(args.plan.read_text(encoding="utf-8")),
                     json.loads(args.queue.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
