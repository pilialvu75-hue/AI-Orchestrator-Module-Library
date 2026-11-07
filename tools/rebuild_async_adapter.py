#!/usr/bin/env python3
"""Rebuild and execute a tested async adapter from an explicit pinned upstream SHA.

Example:
 python tools/rebuild_async_adapter.py --source-commit <40-hex-SHA> --output /tmp/aivexus-async

This is a reproducible development deliverable, NOT Library admission/certification.
Requires git, Dart SDK and network for the first upstream clone/pub resolution.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from build_next_external_dart_adapter import main as _unused  # keep builder import visible
from verify_next_async_admission import verify as _unused_verify

def run(*args, cwd=None):
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("--source-commit must be a full lowercase 40-character Git SHA")
    output = args.output.resolve()
    if output.exists():
        parser.error("output already exists; refusing to overwrite")
    output.mkdir(parents=True)
    upstream = output / "upstream"
    run("git", "clone", "--quiet", "https://github.com/dart-lang/core", upstream)
    run("git", "checkout", "--quiet", args.source_commit, cwd=upstream)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if actual != args.source_commit:
        raise ValueError("pinned source revision mismatch")
    candidate = output / "candidate.json"
    candidate.write_text(json.dumps({"package":"async", "source_commit":actual,
                                      "source_path":"pkgs/async"}, indent=2)+"\n")
    adapter = output / "adapter"
    receipt = output / "adapter-receipt.json"
    run(sys.executable, Path(__file__).with_name("build_next_external_dart_adapter.py"),
        "--candidate", candidate, "--upstream", upstream, "--output", adapter, "--receipt", receipt)
    consumer = output / "consumer"
    (consumer / "bin").mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "examples/async_adapter_consumer/bin/main.dart"
    shutil.copyfile(source, consumer / "bin/main.dart")
    (consumer / "pubspec.yaml").write_text(
        "name: aivexus_async_adapter_consumer\npublish_to: none\n"
        "environment:\n  sdk: ^3.4.0\ndependencies:\n"
        f"  aivexus_external_async:\n    path: {adapter}\n")
    run("dart", "pub", "get", cwd=consumer)
    run("dart", "analyze", cwd=consumer)
    run("dart", "run", "bin/main.dart", cwd=consumer)
    data = json.loads(receipt.read_text())
    data["status"] = "PACKAGED_CONSUMER_PASS"
    data["consumer"] = "examples/async_adapter_consumer/bin/main.dart"
    data["admission_authorized"] = False
    data["certification_authorized"] = False
    receipt.write_text(json.dumps(data, indent=2)+"\n")
    print("PASS: adapter rebuilt and independently executed from", actual)
    print("DELIVERABLE:", adapter)

if __name__ == "__main__":
    main()
