"""Build a research work queue from current needs, not a fixed candidate list."""
import json
from pathlib import Path
import argparse

def plan(root):
    needs = json.loads((root / "catalog/needs.json").read_text())
    result = []
    for need in needs["items"]:
        if need["status"] != "needed":
            continue
        capability = need["capability_id"]
        desired = need["desired_candidates"]
        if type(desired) is not int or desired < 1:
            raise ValueError("invalid desired candidate count")
        result.append({"capability_id": capability, "title": need["title"],
                       "priority": need["priority"], "targets": need["targets"],
                       "desired_candidates": desired,
                       "action": "discover_or_reassess",
                       "requires_independent_functional_contract": True})
    return {"schema": "aivexus.research-work-plan.v1",
            "items": sorted(result, key=lambda r: r["capability_id"])}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args()
    print(json.dumps(plan(args.root), indent=2))

if __name__ == "__main__":
    main()
