#!/usr/bin/env python3
"""Consume a REAL exported LLM-generated TESTED sandbox package as a new Dart app.

This runs on a read-only Linux CI runner after published intake is committed.
It never imports source directly from intake, cannot publish a release, and
does not treat sandbox_preview as production certification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from library_consumer_execution import canonical, safe_path

PIN_PREFIX = "utility.llm_generated."
INDEX_SCHEMA = "ai-orchestrator.library-experimental-index.v1"
ENVELOPE_SCHEMA = "ai-orchestrator.library-module-package-envelope.v1"
PACKAGE_SCHEMA = "ai-orchestrator.library-module-package.v1"


def must(condition, reason):
    if not condition:
        raise ValueError(reason)


def check_run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError(" ".join(command) + " failed: " +
                           (result.stdout + result.stderr)[-1800:])


def candidates(root, specs):
    index = json.loads((root / "packages/experimental-index.json").read_text())
    must(index.get("schema") == INDEX_SCHEMA and
         index.get("certified") is False, "not a sandbox-only index")
    by_id = {spec["id"]: spec for spec in specs}
    rows = []
    for row in index.get("packages", []):
        pin = row.get("pin", "")
        if not pin.startswith(PIN_PREFIX):
            continue
        name = pin[len(PIN_PREFIX):].split("@")[0]
        if name not in by_id:
            continue
        must(pin == PIN_PREFIX + name + "@0.1.0" and
             row.get("tier") == "sandbox_preview" and
             row.get("production_approved") is False,
             "exported module has inconsistent experimental status")
        rows.append((row, by_id[name]))
    must(rows, "no real model-generated TESTED sandbox packages exported")
    return rows


def run_real_consumer(root, row, spec, work):
    rel = str(safe_path(row["path"]))
    must(rel.startswith("packages/experimental/"), "untrusted package path")
    envelope = json.loads((root / rel).read_text(encoding="utf-8"))
    must(envelope.get("schema") == ENVELOPE_SCHEMA, "invalid export envelope")
    pkg = envelope.get("package")
    must(isinstance(pkg, dict) and pkg.get("schema") == PACKAGE_SCHEMA,
         "invalid sandbox package structure")
    digest = hashlib.sha256(canonical(pkg).encode("utf-8")).hexdigest()
    must(digest == row["package_sha256"] == envelope.get("package_sha256"),
         "published package digest mismatch")
    pin = PIN_PREFIX + spec["id"] + "@0.1.0"
    must(pkg.get("pin") == pin and
         pkg.get("tier") == "sandbox_preview" and
         pkg.get("status") == "tested" and
         pkg.get("certified") is False and
         pkg.get("availability") == "experimental" and
         (pkg.get("review") or {}).get("production_approved") is False,
         "export is not an eligible TESTED-only module")
    files = pkg.get("files")
    must(isinstance(files, list) and 1 <= len(files) <= 50,
         "missing or oversized sandbox files")
    package = work / "package"
    package.mkdir()
    seen = set()
    for file in files:
        must(isinstance(file, dict) and isinstance(file.get("content"), str),
             "invalid package source entry")
        name = str(safe_path(file.get("target_path")))
        must(name not in seen, "duplicate package file path")
        seen.add(name)
        dest = package / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(file["content"], encoding="utf-8")
    must({"pubspec.yaml", spec["library_path"],
          "test/independent_contract_test.dart"} <= seen,
         "missing original model source or independent acceptance suite")

    # Create a brand new application rather than using model-written tests.
    app = work / "independent_app"
    (app / "bin").mkdir(parents=True)
    (app / "pubspec.yaml").write_text(
        f"name: p0_final_consumer_{spec['id']}\n"
        "publish_to: none\n"
        "environment:\n  sdk: '>=3.3.0 <4.0.0'\n"
        "dependencies:\n"
        f"  {spec['package_name']}:\n    path: ../package\n",
        encoding="utf-8")
    (app / "bin/main.dart").write_text(spec["consumer_source"],
                                       encoding="utf-8")
    check_run(["dart", "pub", "get", "--offline"], app)
    check_run(["dart", "analyze", "--fatal-infos"], app)
    check_run(["dart", "run", "bin/main.dart"], app)
    return {"pin": pin, "package_sha256": digest,
            "source": "published Library experimental export",
            "independent_dart_consumer": "PASS",
            "certified": False, "production_approved": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    specs = json.loads((root / "examples/real-llm-module-trials.json").read_text())["trials"]
    report = {"schema": "aivexus.llm-published-consumer.v1", "complete": False,
              "certified": False, "items": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        for row, spec in candidates(root, specs):
            with tempfile.TemporaryDirectory(prefix="aivexus-llm-export-") as tmp:
                report["items"].append(run_real_consumer(
                    root, row, spec, Path(tmp)))
        must(report["items"], "no independent consumer executed")
        report["complete"] = True
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report["blocked_reason"] = str(exc)[-1600:]
        raise
    finally:
        args.report.write_text(json.dumps(report, sort_keys=True, indent=2) +
                               "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
