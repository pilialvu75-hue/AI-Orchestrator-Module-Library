#!/usr/bin/env python3
"""Produce a reproducible DISCOVERED-only Library intake candidate from a generated Dart package."""
import argparse
import hashlib
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("output must be empty")
    required = ["pubspec.yaml", "lib/aivexus_running_total.dart", "test/aivexus_running_total_test.dart", "generation.json"]
    files = []
    for name in sorted(required):
        file = package / name
        if not file.is_file():
            raise SystemExit(f"missing generated package file: {name}")
        files.append({"path": name, "content_base64": __import__("base64").b64encode(file.read_bytes()).decode("ascii")})
    payload = json.dumps({"schema": "ai-orchestrator.library-intake-payload.v1", "files": files}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    asset_id = "aivexus.dart.running_total"
    version = "0.1.0"
    manifest = {
        "id": asset_id, "name": "Generated Dart running total", "version": version,
        "kind": "module", "status": "discovered",
        "description": "Deterministically generated and independently tested Dart running totals package; awaiting Library intake gates.",
        "capabilities": ["math.running_total"], "platforms": ["linux"], "languages": ["dart"],
        "entry_paths": ["lib/aivexus_running_total.dart"],
        "provenance": {"origin": "built_in", "source_repository": "https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library", "source_commit": args.source_commit, "source_task_id": "314", "license": None},
        "validation": {"score": 0.8, "tests_passed": True, "test_report": "https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library/actions/runs/42467891123", "validated_on": ["linux"]},
        "security": {"reviewed": False, "notes": "Unreviewed; not certified or trusted for automatic reuse."},
        "integration": {"estimated_effort": "low", "adaptation_allowed": True, "known_constraints": ["Independent consumer tested on Linux CI only; Cantiere integration unverified."]},
        "connector": {"standard": "ai-orchestrator-lego", "standard_version": "1.0.0", "provides": [{"capability_id": "math.running_total", "contract_id": "math.running_total.v1", "contract_version": "1.0"}], "requires": [], "integration_mode": "package"},
        "payload": {"type": "archive", "path": "payload/source.json", "sha256": digest},
    }
    bundle = {
        "schema": "ai-orchestrator.library-intake-bundle.v1",
        "pin": f"{asset_id}@{version}",
        "manifest_path": f"intake/{asset_id}/{version}/manifest.json",
        "payload_path": "payload/source.json",
        "payload_sha256": digest, "payload_json": payload, "manifest": manifest,
    }
    output.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (output / "bundle.json").write_bytes(data)
    (output / "bundle.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(f"DISCOVERED intake candidate {asset_id}@{version}: {digest}")

if __name__ == "__main__":
    main()
