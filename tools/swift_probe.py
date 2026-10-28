"""Discover a source-bound Swift test target and record its outcome, not certification."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from library_source_integrity import payload_tree_sha256

SHA = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")
SCHEMA = "ai-orchestrator.library-swift-probe.v1"
LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "MIT-0"}


class ProbeError(ValueError):
    pass


def read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ProbeError("missing, symlinked or oversized metadata")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProbeError("invalid metadata") from exc
    if not isinstance(result, dict):
        raise ProbeError("metadata root is not an object")
    return result


def lock_is_pinned(source: Path) -> bool:
    try:
        lock = read(source / "Package.resolved")
        pins = lock.get("pins")
        if pins is None:
            pins = (lock.get("object") or {}).get("pins")
        return (isinstance(pins, list) and 0 < len(pins) <= 64
                and all(isinstance(p, dict)
                        and SHA.fullmatch(str((p.get("state") or {}).get("revision", "")))
                        for p in pins))
    except (ProbeError, TypeError):
        return False


def select(root: Path) -> dict:
    for path in sorted((root / "intake").glob("*/*/manifest.json")):
        base = path.parent
        if (base.is_symlink() or base.parent.is_symlink()
                or not ID.fullmatch(base.parent.name) or not VERSION.fullmatch(base.name)):
            continue
        manifest = read(path)
        payload = manifest.get("payload") or {}
        provenance = manifest.get("provenance") or {}
        commit = provenance.get("source_commit")
        digest = payload.get("sha256")
        if (
            manifest.get("id") != base.parent.name
            or manifest.get("version") != base.name
            or manifest.get("status") != "discovered"
            or "swift" not in [str(x).lower() for x in manifest.get("languages", [])]
            or "macos" not in manifest.get("platforms", [])
            or payload.get("type") != "upstream_reference"
            or provenance.get("license") not in LICENSES
            or not isinstance(commit, str) or not SHA.fullmatch(commit)
            or not isinstance(digest, str) or not DIGEST.fullmatch(digest)
            or payload.get("upstream_commit") != commit
            or payload.get("upstream_repository") != provenance.get("source_repository")
        ):
            continue
        source = base / "payload"
        if (source.is_symlink() or not (source / "Package.swift").is_file()
                or not lock_is_pinned(source)
                or not any(p.is_dir() and not p.is_symlink() and p.name.endswith("Tests")
                           for p in source.iterdir())):
            continue
        acquisition = base / "provenance" / "source-acquisition.json"
        if not acquisition.is_file():
            continue
        claim = read(acquisition)
        if (claim.get("source_commit") != commit or claim.get("payload_sha256") != digest
                or claim.get("license_bytes_matched") is not True
                or claim.get("certification_authorized") is not False):
            raise ProbeError("unverified source acquisition claim")
        if payload_tree_sha256(source) != digest:
            raise ProbeError("immutable source digest does not match")
        previous = base / "provenance" / "swift-probe.json"
        if previous.exists():
            result = read(previous)
            if (result.get("schema") == SCHEMA and result.get("source_commit") == commit
                    and result.get("payload_sha256") == digest
                    and result.get("result") in {"passed", "failed"}):
                continue
        return {
            "count": 1, "asset_id": manifest["id"], "version": manifest["version"],
            "source_commit": commit, "payload_sha256": digest,
            "source_path": source.relative_to(root).as_posix(),
        }
    return {"count": 0}


def record(root: Path, plan: dict, claim: dict, job_result: str, run_id: str) -> dict:
    if plan.get("count") != 1 or job_result not in {"success", "failure"}:
        raise ProbeError("unrecognized job outcome")
    asset_id, version = plan["asset_id"], plan["version"]
    if not ID.fullmatch(asset_id) or not VERSION.fullmatch(version):
        raise ProbeError("unsafe asset identity")
    base = root / "intake" / asset_id / version
    manifest = read(base / "manifest.json")
    payload = manifest.get("payload") or {}
    if (manifest.get("status") != "discovered"
            or manifest.get("id") != asset_id or manifest.get("version") != version
            or payload.get("upstream_commit") != plan["source_commit"]
            or payload.get("sha256") != plan["payload_sha256"]
            or payload_tree_sha256(base / "payload") != plan["payload_sha256"]):
        raise ProbeError("candidate or source changed during testing")
    if (claim.get("schema") != "ai-orchestrator.swift-test-run.v1"
            or claim.get("asset_id") != asset_id or claim.get("version") != version
            or claim.get("source_commit") != plan["source_commit"]
            or claim.get("payload_sha256") != plan["payload_sha256"]
            or claim.get("platform") != "macos"
            or type(claim.get("test_exit_code")) is not int
            or (claim["test_exit_code"] == 0) != (job_result == "success")
            or not re.fullmatch(r"\d{5,18}", run_id)):
        raise ProbeError("test receipt not corroborated by GitHub job outcome")
    result = {
        "schema": SCHEMA, "asset_id": asset_id, "version": version,
        "source_commit": plan["source_commit"],
        "payload_sha256": plan["payload_sha256"], "platform": "macos",
        "test_command": "swift test --disable-automatic-resolution -j 2",
        "test_exit_code": claim["test_exit_code"],
        "result": "passed" if job_result == "success" else "failed",
        "github_run_id": run_id, "reviewed": False,
        "certification_authorized": False,
        "scope": "upstream Swift package only; Aivexus connector NOT tested",
    }
    (base / "provenance" / "swift-probe.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    cli = argparse.ArgumentParser()
    sub = cli.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("plan")
    a.add_argument("--root", type=Path, default=Path("."))
    a.add_argument("--output", type=Path, required=True)
    b = sub.add_parser("record")
    b.add_argument("--root", type=Path, default=Path("."))
    b.add_argument("--plan", type=Path, required=True)
    b.add_argument("--result", type=Path, required=True)
    b.add_argument("--job-result", choices=["success", "failure"], required=True)
    b.add_argument("--run-id", required=True)
    args = cli.parse_args()
    try:
        if args.mode == "plan":
            result = select(args.root)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                    out.write(f"count={result['count']}\n")
        else:
            result = record(args.root, read(args.plan), read(args.result),
                            args.job_result, args.run_id)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ProbeError, ValueError) as exc:
        cli.exit(1, f"Swift probe refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
