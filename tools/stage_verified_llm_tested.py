#!/usr/bin/env python3
"""Promote successful real-model *CI source* into TESTED-only Library intake.

This script runs solely in a credential-bearing workflow_run job AFTER the
independent read-only inference/consumer job succeeds. It never runs Dart,
shell commands from model output or any untrusted package. It stages only
declared, SHA-verified source paths and refuses divergent existing assets.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from library_source_integrity import payload_tree_sha256

SOURCE_REPO = "https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library"
VERSION = "0.1.0"
REQUIRED_SOURCE = {"pubspec.yaml", "test/independent_contract_test.dart",
                   "generation.json"}


def _required(condition, message):
    if not condition:
        raise ValueError(message)


def _sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    _required(isinstance(value, dict), "expected JSON object")
    return value


def _data(spec_path, report_path, run_id):
    specs = _load(spec_path)["trials"]
    report = _load(report_path)
    _required(re.fullmatch(r"[0-9]+", run_id) is not None,
              "real run ID must be numeric")
    _required(report.get("schema") == "aivexus.p0-llm-module-consumer.v1"
              and report.get("has_usable_module") is True
              and report.get("certified") is False
              and report.get("production_approved") is False,
              "cannot stage a report with no consumer-PASS module")
    rows = report.get("modules")
    _required(isinstance(rows, list) and len(rows) == len(specs) == 2,
              "both specifications must be attempted and reported")
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict)}
    _required(len(by_id) == len(specs), "duplicate or missing module records")
    passed = {}
    for spec in specs:
        row = by_id.get(spec["id"])
        _required(isinstance(row, dict) and
                  row.get("package") == spec["package_name"],
                  "invalid module record or identity")
        if row.get("status") == "UNVALIDATED":
            _required(row.get("dart_tests") == "BLOCKED"
                      and row.get("separate_consumer") == "BLOCKED",
                      "cannot silently skip ambiguous module status")
            continue
        _required(row.get("status") == "TESTED_IN_ISOLATION_NOT_ADMITTED"
                  and row.get("dart_tests") == "PASS"
                  and row.get("separate_consumer") == "PASS"
                  and str(row.get("model", "")).startswith("ollama-local/")
                  and re.fullmatch(r"[a-f0-9]{64}",
                                   str(row.get("source_sha256", ""))) is not None,
                  "inference or independent consumer evidence missing")
        passed[spec["id"]] = row
    _required(bool(passed), "no independent consumer PASS record")
    _required(report.get("complete") is (len(passed) == len(specs)),
              "contradictory complete/partial result")
    return specs, passed


def _asset(spec):
    return "utility.llm_generated." + spec["id"]


def prepare(source_root, report_path, spec_path, root, run_id, staged_path):
    specs, evidence = _data(spec_path, report_path, run_id)
    staged = []
    for spec in specs:
        module_id = spec["id"]
        if module_id not in evidence:
            print(f"SKIP blocked generated module: {module_id}", flush=True)
            continue
        folder = source_root / module_id
        _required(folder.is_dir() and not folder.is_symlink(),
                  "model package missing")
        entry = spec["library_path"]
        allowed = REQUIRED_SOURCE | {entry}
        _required(re.fullmatch(r"lib/[a-z][a-z0-9_]*[.]dart", entry) is not None,
                  "invalid library entry")
        for rel in allowed:
            file = folder / rel
            _required(file.is_file() and not file.is_symlink()
                      and file.stat().st_size <= 100000,
                      f"missing, symlinked or oversized source: {rel}")
        metadata = _load(folder / "generation.json")
        _required(metadata.get("generator") == "aivexus-llm-candidate-v1"
                  and metadata.get("status") == "UNVALIDATED"
                  and metadata.get("model") == evidence[module_id]["model"],
                  "model provenance does not match successful run")
        _required(_sha_file(folder / entry)
                  == evidence[module_id]["source_sha256"],
                  "generated source differs from independent consumer hash")
        module_id_path = _asset(spec)
        destination = root / "intake" / module_id_path / VERSION
        if destination.exists():
            old = destination / "payload" / "src" / entry
            _required(old.is_file() and
                      _sha_file(old) == evidence[module_id]["source_sha256"],
                      "existing intake is different; never overwrite")
            print(f"SKIP existing immutable TESTED module: {module_id_path}")
            continue
        payload = destination / "payload" / "src"
        payload.mkdir(parents=True, exist_ok=False)
        for rel in sorted(allowed):
            dest = payload / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder / rel, dest)
        staged.append(module_id)
        print(f"STAGED LLM source: {module_id_path}", flush=True)
    staged_path.write_text(
        json.dumps({"run_id": run_id, "modules": staged}, sort_keys=True) + "\n",
        encoding="utf-8")
    return staged


def finalize(root, source_root, report_path, spec_path, staged_path, source_commit):
    receipt = _load(staged_path)
    run_id = receipt["run_id"]
    specs, evidence = _data(spec_path, report_path, run_id)
    _required(re.fullmatch(r"[a-f0-9]{40}", source_commit) is not None,
              "need immutable git source commit")
    staged = set(receipt["modules"])
    _required(staged.issubset({s["id"] for s in specs}),
              "invalid staging list")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")
    for spec in specs:
        if spec["id"] not in staged:
            continue
        module_id = _asset(spec)
        base = root / "intake" / module_id / VERSION
        payload_hash = payload_tree_sha256(base / "payload" / "src")
        cap = "utility.llm_generated." + spec["id"]
        record = evidence[spec["id"]]
        report = {
            "schema": "ai-orchestrator.library-test-report.v1",
            "asset_id": module_id, "version": VERSION,
            "source_commit": source_commit, "passed": True,
            "validated_on": ["linux"],
            "payload_sha256": payload_hash,
            "real_workflow_run": int(run_id),
            "model": record["model"],
            "source_sha256": record["source_sha256"],
            "repairs": record.get("repairs", 0),
            "independent_consumer_executed": True,
            "test_command": (
                "dart pub get && dart analyze --fatal-infos && dart test "
                "&& separate independent Dart consumer"),
        }
        manifest = {
            "id": module_id, "name": "Model-generated Dart " + spec["id"],
            "version": VERSION, "kind": "module", "status": "tested",
            "description": (
                "Original Dart library code generated by local Qwen in "
                "a real public CI run and imported by an independent Dart "
                "consumer. Sandbox only, not security-certified."),
            "capabilities": [cap], "platforms": ["linux"],
            "languages": ["dart"], "entry_paths": [spec["library_path"]],
            "provenance": {
                "origin": "cantiere", "source_repository": SOURCE_REPO,
                "source_commit": source_commit, "source_task_id": "324",
                "license": None,
            },
            "validation": {
                "score": 0.8, "tests_passed": True,
                "test_report": "tests/dart-linux-ci-report.json",
                "validated_at": now, "validated_on": ["linux"],
            },
            "security": {
                "reviewed": False,
                "notes": "No independent security/licensing review. "
                         "Isolated experimentation only; never CERTIFIED.",
            },
            "integration": {
                "estimated_effort": "low", "adaptation_allowed": True,
                "known_constraints": [
                    "Only public Linux runner real-model Dart and independent "
                    "consumer passed; no Android or production host proof.",
                    "No privilege, release or redistribution authorized.",
                ],
            },
            "connector": {
                "standard": "ai-orchestrator-lego", "standard_version": "1.0.0",
                "provides": [{
                    "capability_id": cap, "contract_id": cap + ".v1",
                    "contract_version": "1.0",
                }],
                "requires": [], "integration_mode": "source_bundle",
            },
            "payload": {
                "type": "repository_path", "path": "payload/src",
                "sha256": payload_hash,
            },
        }
        reports = base / "tests"
        reports.mkdir(exist_ok=True)
        (reports / "dart-linux-ci-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        (base / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print("TESTED sandbox ready: " + module_id + "@" + VERSION)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "finalize"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--staged-list", type=Path, required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source, args.report, args.spec, args.root,
                args.run_id, args.staged_list)
    else:
        _required(args.source_commit is not None, "missing source commit")
        finalize(args.root, args.source, args.report, args.spec,
                 args.staged_list, args.source_commit)


if __name__ == "__main__":
    main()
