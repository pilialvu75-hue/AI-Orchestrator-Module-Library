#!/usr/bin/env python3
"""Execute an exported certified Dart package in an unprivileged consumer job.

A passing report requires a real Dart test process; metadata and static checks
alone are never consumer proof. Run only with no repository write permissions.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

SCHEMA = "ai-orchestrator.library-consumer-execution.v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def safe_path(raw):
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ValueError("unsafe package target path")
    p = PurePosixPath(raw)
    if p.is_absolute() or any(x in {"", ".", ".."} for x in raw.split("/")):
        raise ValueError("unsafe package target path")
    if any(x.lower() in {".git", ".dart_tool", "build", "node_modules"} for x in p.parts):
        raise ValueError("unsafe package target path")
    return p


def consume(envelope, *, runner=None):
    if not isinstance(envelope, dict) or envelope.get("schema") != "ai-orchestrator.library-module-package-envelope.v1":
        raise ValueError("invalid certified package envelope")
    package = envelope.get("package")
    if not isinstance(package, dict) or package.get("schema") != "ai-orchestrator.library-module-package.v1":
        raise ValueError("invalid certified package")
    digest = hashlib.sha256(canonical(package).encode("utf-8")).hexdigest()
    if envelope.get("package_sha256") != digest:
        raise ValueError("package SHA256 mismatch")
    if package.get("availability") != "active":
        raise ValueError("consumer requires active certified package")
    files = package.get("files")
    if not isinstance(files, list) or not files or len(files) > 512:
        raise ValueError("missing or oversized package files")
    seen = set()
    with tempfile.TemporaryDirectory(prefix="aivexus-consumer-") as temp:
        root = Path(temp)
        for entry in files:
            if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
                raise ValueError("invalid package file")
            path = safe_path(entry.get("target_path"))
            if str(path) in seen:
                raise ValueError("duplicate package target path")
            seen.add(str(path))
            dest = root.joinpath(*path.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(entry["content"], encoding="utf-8")
        # Only a package with executable tests can count. No tests => no proof.
        if "pubspec.yaml" not in seen or not any(
            p.startswith("test/") and p.endswith("_test.dart") for p in seen
        ):
            raise ValueError("package has no executable Dart behavioral tests")
        if runner is None:
            def runner(command, cwd):
                return subprocess.run(command, cwd=cwd, timeout=180,
                                      capture_output=True, text=True, check=False)
        pub = runner(["dart", "pub", "get"], root)
        if pub.returncode != 0:
            raise ValueError("consumer dart pub get failed")
        result = runner(["dart", "test"], root)
        if result.returncode != 0:
            raise ValueError("consumer Dart behavioral tests failed")
    return {"schema": SCHEMA, "pin": package.get("pin"),
            "package_sha256": digest, "behavioral_test_command": "dart test",
            "consumer_executed": True, "passed": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema": SCHEMA, "consumer_executed": False, "passed": False}
    try:
        report = consume(json.loads(args.package.read_text(encoding="utf-8")))
        code = 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        report["error"] = str(exc)
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
