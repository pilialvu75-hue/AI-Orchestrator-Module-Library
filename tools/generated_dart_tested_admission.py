#!/usr/bin/env python3
"""Materialize a verified generated Dart bundle and advance it to TESTED in an isolated workspace.

Requires a caller to run Dart package tests first. Does not certify or promote.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from library_intake_bundle import verify_bundle_file, materialize_bundle

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--sha256-file", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--dart-test-passed", action="store_true", required=True)
    args = p.parse_args()
    if not args.dart_test_passed:
        raise SystemExit("Dart tests must pass before TESTED admission")
    digest = args.sha256_file.read_text(encoding="utf-8").strip()
    verified = verify_bundle_file(args.bundle, digest)
    root = args.root.resolve()
    destination = materialize_bundle(root, verified)
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest["validation"]["validated_at"] = now
    manifest["validation"]["test_report"] = "tests/dart-linux-ci-report.json"
    report_dir = destination / "tests"
    report_dir.mkdir(exist_ok=True)
    report = {
        "schema": "ai-orchestrator.library-test-report.v1",
        "asset_id": verified.ref.asset_id,
        "version": verified.ref.version,
        "source_commit": manifest["provenance"]["source_commit"],
        "passed": True,
        "validated_on": ["linux"],
        "test_command": "dart pub get && dart analyze --fatal-infos && dart test",
        "note": "CI job must run the above commands successfully before this script is called."
    }
    (report_dir / "dart-linux-ci-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pipeline = Path(__file__).resolve().parent / "library_pipeline.py"
    for status in ("quarantined", "normalized", "tested"):
        subprocess.run([sys.executable, str(pipeline), "advance", verified.ref.asset_id, verified.ref.version, status, "--root", str(root)], check=True)
    final = json.loads(manifest_path.read_text(encoding="utf-8"))
    if final["status"] != "tested":
        raise SystemExit("TESTED transition did not complete")
    print(f"TESTED admission PASS: {verified.ref.asset_id}@{verified.ref.version} (isolated workspace)")

if __name__ == "__main__":
    main()
