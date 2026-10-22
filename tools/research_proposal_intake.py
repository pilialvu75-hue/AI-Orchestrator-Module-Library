#!/usr/bin/env python3
"""Fail-closed, idempotent intake of Researcher knowledge proposals.

This is a planning queue, not an admission or certification mechanism.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HEX = re.compile(r"^[0-9a-f]{64}$")
CAPABILITY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def ingest(root: Path, payload: dict) -> dict:
    if payload.get("schema_version") != 1 or payload.get("kind") != "research_improvement_proposals":
        raise ValueError("unsupported proposal export")
    proposals = payload.get("proposals")
    if not isinstance(proposals, list) or len(proposals) > 1000:
        raise ValueError("invalid proposal batch")
    destination = root / ".airlab" / "research-improvements" / "pending"
    validated = []
    seen = set()
    for item in proposals:
        if not isinstance(item, dict):
            raise ValueError("invalid proposal")
        identifier = item.get("proposal_id")
        capability = item.get("capability_id")
        novelty = item.get("novelty")
        gates = item.get("acceptance_gates")
        if (not isinstance(identifier, str) or not HEX.fullmatch(identifier)
                or not isinstance(capability, str) or not CAPABILITY.fullmatch(capability)
                or item.get("status") != "PROPOSED"
                or not isinstance(novelty, list) or not novelty
                or not all(isinstance(x, str) and 0 < len(x) <= 256 for x in novelty)
                or not isinstance(gates, list) or not gates
                or not all(isinstance(x, str) and 0 < len(x) <= 128 for x in gates)):
            raise ValueError("invalid proposal fields")
        if identifier in seen:
            raise ValueError("duplicate proposal in batch")
        seen.add(identifier)
        validated.append((identifier, item))
    created = 0
    existing = 0
    for identifier, item in validated:
        path = destination / (identifier + ".json")
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("proposal") != item:
                raise ValueError("proposal identifier conflicts with existing content")
            existing += 1
            continue
        destination.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents duplicate writes from concurrent imports.
        with path.open("x", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "state": "AWAITING_TRIAGE",
                       "source": "AI-Orchestrator-Module-Researcher",
                       "proposal": item}, handle, indent=2, sort_keys=True)
            handle.write("\n")
        created += 1
    return {"created": created, "existing": existing, "total": len(validated)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(ingest(args.root, json.loads(args.input.read_text(encoding="utf-8")))))


if __name__ == "__main__":
    main()
