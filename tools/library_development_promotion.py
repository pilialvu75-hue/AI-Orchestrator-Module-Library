#!/usr/bin/env python3
"""Grant INTERNAL DEVELOPMENT qualification from a real exported-package consumer.

This is deliberately NOT security, license, or production certification.
Only a separate read-only Dart-consumer job can supply its PASS receipt.
No model-written code is executed in the credential-bearing publishing job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from library_experimental import preview_package
from library_package import canonical_json

SCHEMA = "aivexus.library.development-qualified-index.v1"
INDEX = "ai-orchestrator.library-experimental-index.v1"
REPORT = "aivexus.llm-published-consumer.v1"
PIN = re.compile(r"(utility[.]llm_generated[.][a-z][a-z0-9_]{1,60})@([0-9]+[.][0-9]+[.][0-9]+)\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"invalid JSON object: {path}")
    return data


def lookup(root):
    index = load(root / "packages" / "experimental-index.json")
    require(index.get("schema") == INDEX and index.get("certified") is False,
            "cannot use a production index")
    entries = index.get("packages")
    require(isinstance(entries, list), "missing sandbox packages")
    by_pin = {}
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("invalid sandbox package row")
        pin = row.get("pin")
        require(isinstance(pin, str) and pin not in by_pin,
                "duplicate or malformed sandbox pin")
        by_pin[pin] = row
    return by_pin


def verify_source_and_package(root, entry, pin, digest):
    match = PIN.fullmatch(pin)
    require(match is not None and SHA.fullmatch(digest) is not None,
            "invalid model-generated pin or SHA256")
    asset, version = match.groups()
    relative = f"packages/experimental/{asset}/{version}/package.json"
    require(entry.get("path") == relative and
            entry.get("package_sha256") == digest and
            entry.get("tier") == "sandbox_preview" and
            entry.get("production_approved") is False,
            "sandbox index and consumer proof disagree")
    original = load(root / relative)
    require(original.get("schema") == "ai-orchestrator.library-module-package-envelope.v1"
            and original.get("package_sha256") == digest,
            "exported package envelope changed")
    package = original.get("package")
    require(isinstance(package, dict) and
            package.get("pin") == pin and
            package.get("certified") is False and
            package.get("status") == "tested" and
            package.get("tier") == "sandbox_preview" and
            (package.get("review") or {}).get("production_approved") is False,
            "exported package is not a TESTED sandbox module")
    actual = hashlib.sha256(canonical_json(package).encode("utf-8")).hexdigest()
    require(actual == digest, "actual exported package differs from proof")
    rebuilt = preview_package(root, asset, version)
    require(rebuilt.get("package_sha256") == digest,
            "source bytes / independently tested manifest no longer match package")
    report_path = root / "intake" / asset / version / "tests/dart-linux-ci-report.json"
    tested = load(report_path)
    require(tested.get("passed") is True and
            tested.get("independent_consumer_executed") is True and
            str(tested.get("model", "")).startswith("ollama-local/") and
            type(tested.get("real_workflow_run")) is int,
            "real original Qwen run and independent source consumer not proven")
    return asset, version, package


def entry_from_proof(root, existing, pin, digest, run_id):
    asset, version, package = verify_source_and_package(root, existing, pin, digest)
    return {
        "pin": pin,
        "path": existing["path"],
        "package_sha256": digest,
        "status": "development_qualified",
        "development_qualified": True,
        "independent_export_consumer": "PASS",
        "consumer_workflow_run_id": run_id,
        "validated_targets": package.get("targets"),
        "security_reviewed": False,
        "license_approved": False,
        "production_certified": False,
        "production_approved": False,
    }


def qualify(root, consumer_path, run_id):
    require(type(run_id) is int and run_id > 0, "invalid trusted consumer run ID")
    receipt = load(consumer_path)
    require(receipt.get("schema") == REPORT and
            receipt.get("complete") is True and
            receipt.get("certified") is False and
            not receipt.get("blocked_reason"),
            "independent exported-package consumer did not complete")
    items = receipt.get("items")
    require(isinstance(items, list) and items, "no real exported-module proof")
    reference = lookup(root)
    rows = {}
    destination = root / "packages" / "development-index.json"
    if destination.is_file():
        prior = load(destination)
        require(prior.get("schema") == SCHEMA and
                prior.get("production_certified") is False and
                prior.get("production_approved") is False,
                "unrecognized existing development index")
        old = prior.get("packages")
        require(isinstance(old, list), "existing development entries invalid")
        for record in old:
            require(isinstance(record, dict), "invalid old development entry")
            pin, digest = record.get("pin"), record.get("package_sha256")
            require(isinstance(pin, str) and pin not in rows,
                    "duplicated old development pin")
            if pin not in reference:
                continue
            require(record.get("development_qualified") is True and
                    record.get("independent_export_consumer") == "PASS" and
                    type(record.get("consumer_workflow_run_id")) is int and
                    record.get("production_certified") is False and
                    record.get("production_approved") is False,
                    "old development record lost its evidence")
            rows[pin] = entry_from_proof(
                root, reference[pin], pin, digest, record["consumer_workflow_run_id"])
    seen = set()
    for item in items:
        require(isinstance(item, dict), "invalid independent consumer result")
        pin, digest = item.get("pin"), item.get("package_sha256")
        require(isinstance(pin, str) and pin not in seen and pin in reference,
                "unknown, duplicate or missing consumed package")
        seen.add(pin)
        require(item.get("independent_dart_consumer") == "PASS" and
                item.get("source") == "published Library experimental export" and
                item.get("certified") is False and
                item.get("production_approved") is False,
                "not a real independently executed TESTED package")
        # Repeated successful consumers must not rewrite the same immutable
        # development qualification or make another Git commit.
        if pin not in rows or rows[pin]["package_sha256"] != digest:
            rows[pin] = entry_from_proof(root, reference[pin], pin, digest, run_id)
    return {
        "schema": SCHEMA,
        "policy": "internal-development-only-no-production-or-redistribution",
        "formal_security_license_review_deferred": True,
        "production_certified": False,
        "production_approved": False,
        "packages": [rows[pin] for pin in sorted(rows)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--consumer-report", type=Path, required=True)
    parser.add_argument("--consumer-run", type=int, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    record = qualify(root, args.consumer_report, args.consumer_run)
    output = root / "packages/development-index.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("Development-qualified original Qwen modules:",
          [x["pin"] for x in record["packages"]])
    print("NOT certified for production; license and security review deferred")


if __name__ == "__main__":
    main()
