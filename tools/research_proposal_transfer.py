#!/usr/bin/env python3
"""Transfer local Researcher proposals into the Library planning queue.

Requires a trusted Researcher checkout and its existing DATA_DIR database.
No remote repository writes, approvals, or execution are performed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sqlite3
import sys
from pathlib import Path

from research_proposal_intake import ingest


def transfer(researcher: Path, library: Path, data_dir: Path, limit: int = 100) -> dict:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    source = researcher.resolve(strict=True)
    if not data_dir.is_dir():
        raise ValueError("Researcher data directory does not exist")
    database = data_dir / "researcher.db"
    if not database.is_file():
        raise ValueError("Researcher state database does not exist")
    # Validate the state file without creating or writing database contents.
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='improvement_proposals'"
        ).fetchone()
    if found is None:
        raise ValueError("Researcher database lacks improvement proposals table")
    if not (source / "src" / "researcher" / "cli.py").is_file():
        raise ValueError("not a Researcher checkout")
    # Avoid inheriting unrelated credentials into the export subprocess.
    allowed = ("PATH", "HOME", "SYSTEMROOT", "WINDIR", "TMPDIR", "TEMP", "TMP")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["DATA_DIR"] = str(data_dir.resolve(strict=True))
    env["PYTHONPATH"] = str(source / "src")
    totals = {"created": 0, "existing": 0, "total": 0}
    offset = 0
    # Bound each invocation while allowing a full backlog to drain over runs.
    for _ in range(100):
        result = subprocess.run(
            [sys.executable, "-m", "researcher", "export-improvement-proposals",
             "--limit", str(limit), "--offset", str(offset)],
            cwd=source,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("invalid Researcher export payload")
        proposals = payload.get("proposals")
        if not isinstance(proposals, list) or len(proposals) > limit:
            raise ValueError("Researcher export exceeded requested page size")
        count = len(proposals)
        page = ingest(library, payload)
        for key in totals:
            totals[key] += page[key]
        if count < limit:
            break
        offset += count
    else:
        raise RuntimeError("proposal export exceeded 100 pages; retry with a larger limit")
    return totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--researcher", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(transfer(args.researcher, args.root, args.data_dir, args.limit)))


if __name__ == "__main__":
    main()
