#!/usr/bin/env python3
"""Pick next original Dart modules without regenerating admitted immutable pins.

The independently authored contracts remain in the trusted repository. Only
the original LLM actually implements Dart source. The selected subset is saved
as an artifact and rechecked by the separate admission publisher, preventing
a model runner from injecting a different specification into a write job.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA = "aivexus.module-llm-trials.v1"
POLICY = "ISOLATED_NONCERTIFIED_NO_AUTOMATIC_RELEASE"


def _contracts(root: Path):
    from run_real_llm_module_trials import read_trials
    return read_trials(root / "examples/real-llm-module-trials.json")


def remaining(root: Path):
    """Unadmitted IDs only. A tested/qualified module is never regenerated."""
    specs = _contracts(root)
    pending = []
    for spec in specs:
        asset = "utility.llm_generated." + spec["id"]
        destination = root / "intake" / asset / "0.1.0"
        formal = root / "modules" / asset / "0.1.0"
        if destination.exists() or formal.exists():
            continue
        pending.append(spec)
    return pending


def select(root: Path, *, offset: int = 0, batch_size: int = 2):
    if type(offset) is not int or offset < 0 or type(batch_size) is not int or not (1 <= batch_size <= 2):
        raise ValueError("invalid selection offset or batch size")
    pending = remaining(root)
    if not pending:
        return {"schema": SCHEMA, "policy": POLICY, "trials": []}
    # Rotate deterministically on scheduled runs. A failed candidate cannot
    # monopolize the first slot forever; it remains eligible for later retry.
    start = offset % len(pending)
    chosen = [pending[(start + index) % len(pending)]
              for index in range(min(batch_size, len(pending)))]
    return {"schema": SCHEMA, "policy": POLICY, "trials": chosen}


def verify_selected(root: Path, selection_path: Path):
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if not isinstance(selection, dict) or set(selection) != {"schema", "policy", "trials"}:
        raise ValueError("unrecognized source trial selection")
    if selection["schema"] != SCHEMA or selection["policy"] != POLICY:
        raise ValueError("unexpected source trial selection policy")
    records = selection["trials"]
    if not isinstance(records, list) or not (1 <= len(records) <= 2):
        raise ValueError("selected 1 or 2 modules required for publication")
    registry = {spec["id"]: spec for spec in _contracts(root)}
    seen = set()
    for spec in records:
        if not isinstance(spec, dict) or not isinstance(spec.get("id"), str):
            raise ValueError("malformed selected contract")
        key = spec["id"]
        if key in seen or key not in registry or registry[key] != spec:
            raise ValueError("selected contract differs from canonical repository")
        seen.add(key)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--batch", type=int, default=2)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.verify is not None:
        verified = verify_selected(root, args.verify)
        print("Verified selected model contracts:", [r["id"] for r in verified])
    else:
        if args.output is None:
            parser.error("--output required for selecting trials")
        record = select(root, offset=args.offset, batch_size=args.batch)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print("Selected new original module specifications:",
              [s["id"] for s in record["trials"]])


if __name__ == "__main__":
    main()
