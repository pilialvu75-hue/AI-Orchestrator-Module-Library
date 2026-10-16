"""Generate a deterministic, read-only coordinator proposal from a work queue.

Queue JSON contains tasks, completed and optional max_parallel. The planner
reads lane occupancy from canonical state. Output is an advisory JSON artifact,
not an authorization to claim, merge, approve, or certify anything.
"""
import argparse
import json
from pathlib import Path

from plan_parallel_work import plan_from_canonical


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    tasks = queue.get("tasks", [])
    result = plan_from_canonical(
        args.root, tasks, queue.get("max_parallel"), queue.get("completed", [])
    )
    result["queue_revision"] = queue.get("revision")
    result["completed"] = queue.get("completed", [])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
