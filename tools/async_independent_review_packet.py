"""Generate an unsigned, source-bound review packet for the real TESTED async intake.

This is evidence preparation, never an independent review or certification.
"""
import argparse
import hashlib
import json
from pathlib import Path

from library_evidence import verify_manifest_evidence
from library_source_integrity import payload_tree_sha256

ASSET = "utility.async_stream_queue.external.dartlang.async"
VERSION = "0.1.0"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(root):
    base = root / "intake" / ASSET / VERSION
    manifest = json.loads((base / "manifest.json").read_text())
    if (manifest["id"] != ASSET or manifest["version"] != VERSION
            or manifest["status"] != "tested"
            or manifest["security"]["reviewed"] is not False):
        raise ValueError("expected unreviewed TESTED async candidate")
    verify_manifest_evidence(base, manifest)
    source = base / manifest["payload"]["path"]
    digest = payload_tree_sha256(source)
    if digest != manifest["payload"]["sha256"]:
        raise ValueError("source digest mismatch")
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink not allowed in review inventory")
        if path.is_file():
            files.append({"path": path.relative_to(source).as_posix(),
                          "sha256": sha(path), "bytes": path.stat().st_size})
    if not files or len(files) > 512:
        raise ValueError("source inventory must contain 1-512 files")
    license_file = base / manifest["provenance"]["license_file"]
    original = source / "vendor/async/LICENSE"
    if not license_file.is_file() or license_file.read_bytes() != original.read_bytes():
        raise ValueError("license attribution differs from original source")
    upstream = source / "vendor/async/pubspec.yaml"
    if not upstream.is_file():
        raise ValueError("original upstream package metadata missing")
    report = json.loads((base / manifest["validation"]["test_report"]).read_text())
    return {
        "schema": "aivexus.library.async-independent-review-request.v1",
        "asset_id": ASSET, "version": VERSION,
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "source": {
            "repository": manifest["provenance"]["source_repository"],
            "commit": manifest["provenance"]["source_commit"],
            "payload_tree_sha256": digest,
            "license_sha256": sha(license_file),
            "file_inventory": files,
        },
        "test_evidence": {
            "ci_run_id": report["evidence"]["github_run_id"],
            "ci_commit": report["evidence"]["github_commit"],
            "validated_on": manifest["validation"]["validated_on"],
            "test_report_sha256": sha(base / manifest["validation"]["test_report"]),
        },
        "sbom": {
            "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "metadata": {"component": {"type": "library", "name": ASSET, "version": VERSION}},
            "components": [
                {"type": "library", "name": "async", "version": "upstream-pinned",
                 "properties": [{"name": "aivexus:upstream_commit",
                                 "value": manifest["provenance"]["source_commit"]}]},
                {"type": "library", "name": "aivexus_external_async", "version": VERSION,
                 "properties": [{"name": "aivexus:payload_sha256", "value": digest}]},
            ],
        },
        "review_tasks": [
            "Verify full source and transitive dependency inventory",
            "Validate BSD-3-Clause license obligations and attribution",
            "Perform independent security, privacy and vulnerability assessment",
            "Approve SBOM and sign exact source/license/SBOM with protected Ed25519 reviewer",
            "Run host-platform consumer tests before distribution",
        ],
        "sbom_complete": False,
        "vulnerability_scan_completed": False,
        "security_reviewed": False,
        "certification_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = generate(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"asset_id": ASSET, "files": len(packet["source"]["file_inventory"]),
                      "certification_authorized": False}))


if __name__ == "__main__":
    main()
