"""Fail closed when the advisory planner selects an ineligible lane task.

The queue audit must be a real gate, not just an uploaded artifact.
"""
import argparse
import json
from pathlib import Path


def gate(plan, audit):
    findings = audit.get("findings", [])
    by_task = {}
    for finding in findings:
        task = finding.get("task")
        if not isinstance(task, str) or task in by_task:
            raise ValueError("missing or duplicate queue audit task")
        by_task[task] = finding
    for assignment in plan.get("assignments", []):
        task = assignment.get("task")
        finding = by_task.get(task)
        if finding is None:
            raise ValueError("assignment has no audit finding: " + str(task))
        if finding.get("lane") != assignment.get("lane"):
            raise ValueError("assignment lane differs from audit: " + str(task))
        if finding.get("eligible") is not True:
            raise ValueError("ineligible assignment blocked: " + str(task))
    return {"gate": "PASS", "checked": len(plan.get("assignments", []))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = gate(json.loads(a.plan.read_text(encoding="utf-8")),
                  json.loads(a.audit.read_text(encoding="utf-8")))
    a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
