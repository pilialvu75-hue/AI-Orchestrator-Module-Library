"""Source-bound triage of the async test-only dart:io static finding.

This records reproducible context, NOT an independent security sign-off.
"""
import argparse
import hashlib
import json
from pathlib import Path

ASSET = "utility.async_stream_queue.external.dartlang.async"
TEST_PATH = "vendor/async/test/io_sink_impl.dart"


def triage(root: Path, packet: dict, audit: dict) -> dict:
    if packet.get("asset_id") != ASSET or audit.get("asset_id") != ASSET:
        raise ValueError("asset identity mismatch")
    source = packet["source"]
    digest = source["payload_tree_sha256"]
    if audit.get("source_payload_sha256") != digest:
        raise ValueError("static audit source digest mismatch")
    inventory = source["file_inventory"]
    entries = [entry for entry in inventory if entry.get("path") == TEST_PATH]
    if len(entries) != 1:
        raise ValueError("expected test source absent or duplicated")
    findings = audit.get("findings")
    if not isinstance(findings, list) or len(findings) != 1:
        raise ValueError("unexpected static findings; manual review required")
    finding = findings[0]
    if finding != {"file": TEST_PATH, "rule": "SENSITIVE_IMPORT", "import": "dart:io"}:
        raise ValueError("static finding changed; manual review required")
    source_file = root / "intake" / ASSET / packet["version"] / "payload" / "src" / TEST_PATH
    raw = source_file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entries[0]["sha256"] or len(raw) != entries[0]["bytes"]:
        raise ValueError("test source file does not match inventoried bytes")
    text = raw.decode("utf-8")
    if "import 'dart:io';" not in text or "class IOSinkImpl extends IOSinkBase implements IOSink" not in text:
        raise ValueError("test source content changed")
    return {
        "schema": "aivexus.library.async-static-finding-triage.v1",
        "asset_id": ASSET,
        "source_payload_sha256": digest,
        "finding": finding,
        "file_sha256": entries[0]["sha256"],
        "classification": "TEST_ONLY_DART_IO_IMPORT_REQUIRES_REVIEW",
        "observed_context": "Test helper declares IOSinkImpl implementing IOSink, using dart:io types",
        "independent_security_reviewed": False,
        "certification_authorized": False,
        "manual_review_required": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = triage(args.root, json.loads(args.packet.read_text()), json.loads(args.audit.read_text()))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["classification"])


if __name__ == "__main__":
    main()
