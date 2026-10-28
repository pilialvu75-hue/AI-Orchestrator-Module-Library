"""Autonomous native Swift diagnostics adapter: builder, selection, and receipt.

The builder never executes upstream code. macOS untrusted CI validates the
generated adapter; the trusted recorder cannot certify/promote modules.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

from library_source_integrity import payload_tree_sha256
from swift_probe import TOOLCHAIN_PROFILE, read

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path("tools/swift_adapters/diagnostics.logging.v1")
CONTRACT = "diagnostics.logging.v1"
SCHEMA = "ai-orchestrator.library-swift-adapter-proof.v1"
RESULT_SCHEMA = "ai-orchestrator.swift-adapter-test-run.v1"
SHA = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")
TARGET = "macos"


class AdapterError(ValueError):
    pass


def _bridge(root: Path) -> Path:
    source = root / TEMPLATES
    if not (source / "Sources/AivexusDiagnosticsLoggingBridge.swift").is_file():
        raise AdapterError("trusted diagnostics.logging.v1 bridge source missing")
    if not (source / "Tests/AivexusDiagnosticsBridgeTests.swift").is_file():
        raise AdapterError("trusted diagnostics.logging.v1 bridge tests missing")
    return source


def _verified_candidate(root: Path, base: Path) -> dict | None:
    if base.is_symlink() or base.parent.is_symlink():
        return None
    if not ID.fullmatch(base.parent.name) or not VERSION.fullmatch(base.name):
        return None
    data = read(base / "manifest.json")
    payload = data.get("payload") or {}
    upstream = data.get("provenance") or {}
    if (
        data.get("id") != base.parent.name
        or data.get("version") != base.name
        or data.get("status") not in {"discovered", "tested"}
        or data.get("capabilities") != ["diagnostics.logging"]
        or "swift" not in [str(x).lower() for x in data.get("languages", [])]
        or TARGET not in data.get("platforms", [])
        or payload.get("type") != "upstream_reference"
        or not isinstance(payload.get("sha256"), str)
        or not DIGEST.fullmatch(payload["sha256"])
        or not isinstance(upstream.get("source_commit"), str)
        or not SHA.fullmatch(upstream["source_commit"])
        or payload.get("upstream_commit") != upstream["source_commit"]
    ):
        return None
    provides = (data.get("connector") or {}).get("provides") or []
    if not any(isinstance(p, dict) and p.get("contract_id") == CONTRACT for p in provides):
        return None
    src = base / "payload"
    if src.is_symlink() or not src.is_dir():
        return None
    if payload_tree_sha256(src) != payload["sha256"]:
        raise AdapterError("immutable source digest mismatch")
    manifest = (src / "Package.swift").read_text(encoding="utf-8")
    if (manifest.count("    targets: [\n") != 1
            or '.library(name: "Diagnostics", targets: ["Diagnostics"])' not in manifest):
        return None
    logger = src / "Sources/Logging/DiagnosticsLogger.swift"
    if not logger.is_file():
        return None
    api = logger.read_text(encoding="utf-8")
    if not all(s in api for s in (
        "public final class DiagnosticsLogger:",
        "public static func setup() throws",
        "public static func log(message: String",
        "public static func isSetUp() -> Bool",
    )):
        return None
    proof_path = base / "provenance" / "swift-probe.json"
    if not proof_path.is_file():
        return None
    proof = read(proof_path)
    if (
        proof.get("result") != "passed"
        or proof.get("certification_authorized") is not False
        or proof.get("toolchain_profile") != TOOLCHAIN_PROFILE
        or proof.get("source_commit") != upstream["source_commit"]
        or proof.get("payload_sha256") != payload["sha256"]
    ):
        return None
    return {
        "count": 1,
        "asset_id": data["id"],
        "version": data["version"],
        "source_commit": upstream["source_commit"],
        "payload_sha256": payload["sha256"],
        "contract_id": CONTRACT,
        "platform": TARGET,
        "toolchain_profile": TOOLCHAIN_PROFILE,
        "source_path": src.relative_to(root).as_posix(),
    }


def plan(root: Path) -> dict:
    template_digest = payload_tree_sha256(_bridge(root))
    for file in sorted((root / "intake").glob("*/*/manifest.json")):
        row = _verified_candidate(root, file.parent)
        if row is None:
            continue
        row["adapter_sha256"] = template_digest
        previous = file.parent / "provenance" / "swift-adapter.json"
        if previous.is_file():
            old = read(previous)
            if all(old.get(k) == row[k] for k in (
                "asset_id", "version", "source_commit", "payload_sha256",
                "adapter_sha256", "contract_id", "platform", "toolchain_profile",
            )) and old.get("result") in {"passed", "failed"}:
                continue
        return row
    return {"count": 0}


def stage(root: Path, selection: dict, output: Path) -> dict:
    actual = plan(root)
    if selection != actual or actual.get("count") != 1:
        raise AdapterError("source, bridge template or previous test state changed")
    if output.exists() or output.is_symlink():
        raise AdapterError("staging directory must be new")
    src = root / selection["source_path"]
    shutil.copytree(src, output)
    original = output / "Package.swift"
    content = original.read_text(encoding="utf-8")
    needle = "    targets: [\n"
    if content.count(needle) != 1:
        raise AdapterError("unsupported SwiftPM manifest target layout")
    insert = (
        '        .target(name: "AivexusDiagnosticsLoggingBridge", '
        'dependencies: ["Diagnostics"], path: "AivexusDiagnosticsLoggingBridge"),\n'
        '        .testTarget(name: "AivexusDiagnosticsBridgeTests", '
        'dependencies: ["AivexusDiagnosticsLoggingBridge", "Diagnostics"], '
        'path: "AivexusDiagnosticsBridgeTests"),\n'
    )
    original.write_text(content.replace(needle, needle + insert), encoding="utf-8")
    adapter = _bridge(root)
    bridge_dir = output / "AivexusDiagnosticsLoggingBridge"
    test_dir = output / "AivexusDiagnosticsBridgeTests"
    bridge_dir.mkdir()
    test_dir.mkdir()
    shutil.copyfile(
        adapter / "Sources/AivexusDiagnosticsLoggingBridge.swift",
        bridge_dir / "AivexusDiagnosticsLoggingBridge.swift",
    )
    shutil.copyfile(
        adapter / "Tests/AivexusDiagnosticsBridgeTests.swift",
        test_dir / "AivexusDiagnosticsBridgeTests.swift",
    )
    return selection


def record(root: Path, selection: dict, result: dict, job_result: str, run_id: str) -> dict:
    if selection.get("count") != 1 or job_result not in {"success", "failure"}:
        raise AdapterError("unsupported integration job state")
    identity = selection.get("asset_id")
    version = selection.get("version")
    if not isinstance(identity, str) or not ID.fullmatch(identity):
        raise AdapterError("unsafe asset ID")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise AdapterError("unsafe version")
    if not re.fullmatch(r"[0-9]{5,18}", run_id):
        raise AdapterError("untrusted run identifier")
    now = plan(root)
    if now != selection:
        raise AdapterError("candidate or adapter changed during integration run")
    required = (
        "asset_id", "version", "source_commit", "payload_sha256",
        "adapter_sha256", "contract_id", "platform", "toolchain_profile",
    )
    if (
        result.get("schema") != RESULT_SCHEMA
        or not all(result.get(key) == selection[key] for key in required)
        or type(result.get("test_exit_code")) is not int
        or (result["test_exit_code"] == 0) != (job_result == "success")
    ):
        raise AdapterError("untrusted adapter receipt contradicts plan or CI job outcome")
    receipt = {
        **{k: selection[k] for k in required},
        "schema": SCHEMA,
        "result": "passed" if job_result == "success" else "failed",
        "test_exit_code": result["test_exit_code"],
        "test_command": "swift test --disable-automatic-resolution -j 2 --filter AivexusDiagnosticsBridgeTests",
        "github_run_id": run_id,
        "has_executable_bridge_source": True,
        "integration_scope": "macOS native diagnostics.logging.v1 adapter smoke, redaction and rejection tests",
        "independent_security_reviewed": False,
        "certification_authorized": False,
        "release_eligible": False,
    }
    file = root / "intake" / identity / version / "provenance" / "swift-adapter.json"
    file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd", required=True)
    a = subs.add_parser("plan")
    a.add_argument("--root", type=Path, default=ROOT)
    a.add_argument("--output", type=Path, required=True)
    b = subs.add_parser("stage")
    b.add_argument("--root", type=Path, default=ROOT)
    b.add_argument("--plan", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    c = subs.add_parser("record")
    c.add_argument("--root", type=Path, default=ROOT)
    c.add_argument("--plan", type=Path, required=True)
    c.add_argument("--result", type=Path, required=True)
    c.add_argument("--job-result", choices=["success", "failure"], required=True)
    c.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "plan":
            outcome = plan(args.root)
            args.output.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
                    handle.write(f"count={outcome['count']}\n")
        elif args.cmd == "stage":
            outcome = stage(args.root, read(args.plan), args.output)
        else:
            outcome = record(args.root, read(args.plan), read(args.result),
                             args.job_result, args.run_id)
        print(json.dumps(outcome, sort_keys=True))
        return 0
    except (AdapterError, OSError, ValueError) as exc:
        parser.exit(1, f"Swift adapter refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
