"""Export a real, SHA256-bound Swift source + Aivexus adapter for isolated tests.

An immutable source archive for an unapproved candidate is NOT a certified
module, a production package or a permission to run third-party code in apps.
Nothing is executed by this exporter.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path

from library_evidence import verify_test_evidence
from library_source_integrity import payload_tree_sha256
from swift_adapter import CONTRACT, _bridge, _verified_candidate, assemble_pinned_source
from swift_probe import read

SCHEMA = "ai-orchestrator.swift-sandbox-source-bundle.v1"
PROOF_SCHEMA = "ai-orchestrator.library-swift-adapter-proof.v1"
HASH = re.compile(r"[a-f0-9]{64}\Z")
MAX_FILES = 512
MAX_BYTES = 20 * 1024 * 1024


class SandboxBundleError(ValueError):
    pass


def select(root: Path) -> dict:
    template_hash = payload_tree_sha256(_bridge(root))
    for path in sorted((root / "intake").glob("*/*/manifest.json")):
        base = path.parent
        manifest = read(path)
        if manifest.get("status") != "tested" or (
            manifest.get("security") or {}
        ).get("reviewed") is True:
            continue
        candidate = _verified_candidate(root, base)
        if candidate is None:
            continue
        adapter_path = base / "provenance/swift-adapter.json"
        report_path = base / "evidence/test-report.json"
        preflight_path = base / "evidence/security-preflight.json"
        if not all(x.is_file() and not x.is_symlink()
                   for x in (adapter_path, report_path, preflight_path)):
            continue
        adapter = read(adapter_path)
        report = read(report_path)
        preflight = read(preflight_path)
        source_hash = candidate["payload_sha256"]
        source_commit = candidate["source_commit"]
        if not (
            adapter.get("schema") == PROOF_SCHEMA
            and adapter.get("result") == "passed"
            and adapter.get("certification_authorized") is False
            and adapter.get("independent_security_reviewed") is False
            and adapter.get("adapter_sha256") == template_hash
            and adapter.get("payload_sha256") == source_hash
            and adapter.get("source_commit") == source_commit
            and adapter.get("contract_id") == CONTRACT
            and adapter.get("platform") == "macos"
            and report.get("schema") == "ai-orchestrator.library-test-report.v1"
            and report.get("passed") is True
            and report.get("payload_sha256") == source_hash
            and report.get("source_commit") == source_commit
            and report.get("adapter_sha256") == template_hash
            and report.get("validated_on") == ["macos"]
            and report.get("evidence", {}).get("adapter_github_run_id") == adapter.get("github_run_id")
            and preflight.get("schema") == "ai-orchestrator.swift-security-preflight.v1"
            and preflight.get("reviewed") is False
            and preflight.get("certification_authorized") is False
            and preflight.get("payload_sha256") == source_hash
            and preflight.get("source_commit") == source_commit
            and isinstance(preflight.get("sbom_sha256"), str)
            and HASH.fullmatch(preflight["sbom_sha256"])
        ):
            raise SandboxBundleError("source, current bridge, protected tests or security preflight mismatch")
        sbom_path = base / "evidence/sbom.cdx.json"
        if not sbom_path.is_file() or sbom_path.is_symlink():
            raise SandboxBundleError("verified source dependency SBOM missing")
        if hashlib.sha256(sbom_path.read_bytes()).hexdigest() != preflight["sbom_sha256"]:
            raise SandboxBundleError("security SBOM was changed after the preflight")
        try:
            verify_test_evidence(base, manifest)
        except Exception as exc:
            raise SandboxBundleError("cannot verify real source-bound test report") from exc
        return {
            **candidate,
            "adapter_sha256": template_hash,
            "adapter_github_run_id": adapter["github_run_id"],
            "upstream_github_run_id": report["evidence"]["upstream_github_run_id"],
            "sbom_sha256": preflight["sbom_sha256"],
            "security_reviewed": False,
            "certification_authorized": False,
            "sandbox_only": True,
        }
    return {"count": 0}


def _make_archive(source: Path, target: Path) -> tuple[str, int]:
    files = sorted((p for p in source.rglob("*") if p.is_file()), key=lambda x: x.relative_to(source).as_posix())
    if len(files) == 0 or len(files) > MAX_FILES:
        raise SandboxBundleError("oversized or empty isolated source package")
    total = 0
    for item in files:
        if item.is_symlink() or not item.resolve().is_relative_to(source.resolve()):
            raise SandboxBundleError("symlinks or source escapes are not allowed")
        total += item.stat().st_size
        if total > MAX_BYTES:
            raise SandboxBundleError("sandbox bundle exceeds strict size limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for file in files:
                    data = file.read_bytes()
                    metadata = tarfile.TarInfo(file.relative_to(source).as_posix())
                    metadata.size = len(data)
                    metadata.mode = 0o644
                    metadata.uid = metadata.gid = metadata.mtime = 0
                    metadata.uname = metadata.gname = ""
                    tar.addfile(metadata, io.BytesIO(data))
    return hashlib.sha256(target.read_bytes()).hexdigest(), len(files)


def export(root: Path, target: Path) -> dict:
    root = root.resolve()
    candidate = select(root)
    if candidate.get("count") != 1:
        return {"count": 0}
    if target.is_symlink():
        raise SandboxBundleError("unsafe sandbox bundle output path")
    with tempfile.TemporaryDirectory(prefix="aivexus-swift-sandbox-") as work:
        staging = Path(work) / "source"
        assemble_pinned_source(root, candidate, staging)
        notice = {
            "schema": SCHEMA,
            **{key: candidate[key] for key in (
                "asset_id", "version", "source_commit", "payload_sha256",
                "adapter_sha256", "contract_id", "platform",
                "upstream_github_run_id", "adapter_github_run_id", "sbom_sha256",
            )},
            "source": "verified immutable upstream with Aivexus native Swift logging adapter overlay",
            "execution_policy": "isolated-macos-developer-test-only",
            "production_approved": False,
            "security_reviewed": False,
            "certification_authorized": False,
            "runtime_warning": (
                "Running DiagnosticsLogger.setup() with explicit opt-in intercepts "
                "process-wide stdout/stderr and may read environment or metrics. "
                "Use only an isolated test account/VM without secrets, never production."
            ),
        }
        (staging / "AIVEXUS_SANDBOX_ONLY.json").write_text(
            json.dumps(notice, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        checksum, count = _make_archive(staging, target)
    return {
        "count": 1,
        "asset_id": candidate["asset_id"],
        "version": candidate["version"],
        "bundle_sha256": checksum,
        "source_sha256": candidate["payload_sha256"],
        "adapter_sha256": candidate["adapter_sha256"],
        "file_count": count,
        "sandbox_only": True,
        "production_approved": False,
        "certification_authorized": False,
    }


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    cli.add_argument("--archive", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    try:
        result = export(args.root, args.archive)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                out.write(f"count={result['count']}\n")
        print(json.dumps(result, sort_keys=True))
    except (SandboxBundleError, OSError, ValueError) as exc:
        cli.exit(1, f"Swift sandbox source export refused: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
