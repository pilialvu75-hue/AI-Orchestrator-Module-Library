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
import sys
from pathlib import Path

from research_proposal_intake import ingest


def transfer(researcher: Path, library: Path, data_dir: Path, limit: int = 100) -> dict:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    source = researcher.resolve(strict=True)
    if not (source / "src" / "researcher" / "cli.py").is_file():
        raise ValueError("not a Researcher checkout")
    env = dict(os.environ)
    env["DATA_DIR"] = str(data_dir.resolve(strict=True))
    env["PYTHONPATH"] = str(source / "src")
    result = subprocess.run(
        [sys.executable, "-m", "researcher", "export-improvement-proposals",
         "--limit", str(limit)],
        cwd=source,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(result.stdout)
    return ingest(library, payload)


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
