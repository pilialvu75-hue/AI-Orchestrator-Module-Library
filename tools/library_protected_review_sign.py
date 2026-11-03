#!/usr/bin/env python3
"""Protected reviewer signer. Never runs candidate code or approves a candidate.

The independently reviewed statement must be supplied by the reviewer; this
tool only signs exact canonical bytes using a protected Ed25519 private key.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

FIELDS = {"schema", "asset_id", "version", "source_commit", "payload_sha256",
          "sbom_sha256", "license_file_sha256", "reviewed_at", "reviewer_id",
          "known_vulnerabilities", "decision"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def sign(statement, private_pem):
    if not isinstance(statement, dict) or set(statement) != FIELDS:
        raise ValueError("reviewer statement fields mismatch")
    if statement["schema"] != "ai-orchestrator.library-review-authorization.v1":
        raise ValueError("unsupported review authorization schema")
    if statement["decision"] != "APPROVED" or type(statement["known_vulnerabilities"]) is not int or statement["known_vulnerabilities"] != 0:
        raise ValueError("reviewer has not approved a zero-known-vulnerability candidate")
    if not isinstance(statement["source_commit"], str) or not COMMIT.fullmatch(statement["source_commit"]):
        raise ValueError("invalid immutable source commit")
    for name in ("payload_sha256", "sbom_sha256", "license_file_sha256"):
        if not isinstance(statement[name], str) or not SHA.fullmatch(statement[name]):
            raise ValueError("missing source-bound evidence digest")
    if not isinstance(statement["reviewer_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{1,127}", statement["reviewer_id"]):
        raise ValueError("missing independent reviewer identity")
    for name in ("asset_id", "version", "reviewed_at"):
        if not isinstance(statement[name], str) or not statement[name].strip():
            raise ValueError("missing reviewer statement metadata")
    if not isinstance(private_pem, str) or "-----BEGIN PRIVATE KEY-----" not in private_pem:
        raise ValueError("protected signing key unavailable")
    payload = b"AI-ORCHESTRATOR-LOCAL-REVIEW-v1\n" + json.dumps(
        statement, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    with tempfile.TemporaryDirectory(prefix="protected-review-") as folder:
        root = Path(folder)
        key = root / "key.pem"
        message = root / "statement.bin"
        key.write_text(private_pem, encoding="ascii")
        key.chmod(0o600)
        message.write_bytes(payload)
        check = subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"],
                               capture_output=True, check=False, timeout=8)
        if check.returncode or len(check.stdout) != 44 or not check.stdout.startswith(bytes.fromhex("302a300506032b6570032100")):
            raise ValueError("protected private key must be Ed25519")
        result = subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key),
                                 "-rawin", "-in", str(message)], capture_output=True,
                                check=False, timeout=8)
        if result.returncode or len(result.stdout) != 64:
            raise ValueError("protected Ed25519 signing failed")
    return {"algorithm": "ed25519-openssl-v1", "statement": statement,
            "signature_base64": base64.b64encode(result.stdout).decode("ascii")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    statement = json.loads(args.statement.read_text(encoding="utf-8"))
    result = sign(statement, os.environ.get("LIBRARY_SECURITY_REVIEW_PRIVATE_KEY_PEM", ""))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("Protected reviewer signature generated; no certification or publication performed.")


if __name__ == "__main__":
    main()
