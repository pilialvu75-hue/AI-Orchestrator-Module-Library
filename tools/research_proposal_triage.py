#!/usr/bin/env python3
"""Read-only, deterministic triage report for pending Researcher proposals.

Similarity is a review hint, not proof of duplication or module eligibility.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def report(root: Path) -> dict:
    pending = root / ".airlab" / "research-improvements" / "pending"
    rows = []
    for path in sorted(pending.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        proposal = record["proposal"]
        identifier = proposal["proposal_id"]
        if (path.stem != identifier or record["state"] != "AWAITING_TRIAGE"
                or proposal["status"] != "PROPOSED"):
            raise ValueError(f"invalid pending record: {path.name}")
        rows.append(proposal)

    by_capability = Counter(row["capability_id"] for row in rows)
    exact = defaultdict(list)
    for row in rows:
        signature = (
            row["capability_id"],
            tuple(sorted(set(row["novelty"]))),
            tuple(sorted(set(row["acceptance_gates"]))),
        )
        exact[signature].append(row["proposal_id"])
    duplicates = [
        sorted(ids) for ids in exact.values() if len(ids) > 1
    ]
    duplicates.sort()
    return {
        "schema_version": 1,
        "kind": "research_proposal_triage_report",
        "total_pending": len(rows),
        "by_capability": dict(sorted(by_capability.items())),
        "exact_metadata_duplicate_groups": duplicates,
        "duplicate_review_count": sum(len(group) - 1 for group in duplicates),
        "requires_human_or_worker_validation": True,
        "modules_created": 0,
        "records_modified": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(report(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
