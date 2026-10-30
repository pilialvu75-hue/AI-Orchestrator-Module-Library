"""Fail-closed intake gate for a source bundle received from autonomous Researcher.

Validates exact git blobs and source tree hash BEFORE any Dart code is run.
No security or certification status can be derived from this preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from library_source_integrity import SourceIntegrityError, payload_tree_sha256

SOURCE_REPOSITORY = "https://github.com/dart-lang/core"
PROFILES = {"path": "platform.filesystem",
            "characters": "platform.filesystem",
            "fixnum": "platform.process"}
SHA40 = re.compile(r"[a-f0-9]{40}$")
SHA256 = re.compile(r"[a-f0-9]{64}$")
VERSION = re.compile(r"[0-9]+[.][0-9]+[.][0-9]+$")
MAX_FILES = 400


class AutonomousSourceError(ValueError):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise AutonomousSourceError(reason)


def inspect(root: Path, package: str) -> dict:
    require(package in PROFILES, "unsupported unreviewed module profile")
    base = root / "sandbox/researcher_public_dart" / package
    manifest = base / "metadata.json"
    require(manifest.is_file() and not manifest.is_symlink(),
            "real Researcher source and evidence are missing")
    require(manifest.stat().st_size <= 65536, "oversized or untrusted metadata")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    require(data.get("schema") == "aivexus.researcher.autonomous-public-dart-intake.v1",
            "unrecognized Researcher handoff")
    require(data.get("package") == package
            and data.get("capability_id") == PROFILES[package]
            and data.get("state") == "NORMALIZED_NOT_TESTED",
            "candidate identity or lifecycle differs")
    require(data.get("source_repository") == SOURCE_REPOSITORY
            and data.get("source_subtree") == "pkgs/" + package
            and data.get("source_license") == "BSD-3-Clause",
            "missing precise public provenance/license")
    version = data.get("package_version")
    require(isinstance(version, str) and VERSION.fullmatch(version) is not None
            and data.get("source_tag") == package + "-v" + version,
            "unverified stable tag identity")
    sha = data.get("source_commit")
    require(isinstance(sha, str) and SHA40.fullmatch(sha) is not None,
            "un-pinned source commit")
    expected = data.get("payload_sha256")
    require(isinstance(expected, str) and SHA256.fullmatch(expected) is not None,
            "missing source tree SHA256")
    require(data.get("source_materialized") is True
            and data.get("upstream_files", 0) > 0
            and data.get("source_tests_executed") is not True
            and data.get("independent_security_reviewed") is False
            and data.get("certification_authorized") is False
            and data.get("production_installation_authorized") is False,
            "Researcher cannot self-certify or claim unrun tests")
    source = base / "payload/src"
    require(source.is_dir() and not source.is_symlink(),
            "source payload missing")
    try:
        digest = payload_tree_sha256(source)
    except (SourceIntegrityError, OSError) as exc:
        raise AutonomousSourceError("invalid materialized source tree") from exc
    require(digest == expected, "immutable source SHA256 changed")
    blobs = data.get("source_git_blobs")
    require(isinstance(blobs, dict) and 1 <= len(blobs) <= MAX_FILES,
            "missing bounded original Git blob inventory")
    originals = source / "vendor" / package
    require(originals.is_dir() and not originals.is_symlink(),
            "original public upstream package absent")
    files = {x.relative_to(originals).as_posix(): x
             for x in originals.rglob("*") if x.is_file()}
    require(set(files) == set(blobs), "injected, omitted or renamed original Git file")
    for name, git_hash in blobs.items():
        require(isinstance(name, str) and name and not name.startswith("/")
                and chr(92) not in name
                and all(p not in ("", ".", "..") for p in name.split("/")),
                "unsafe original Git path")
        require(isinstance(git_hash, str) and SHA40.fullmatch(git_hash) is not None,
                "missing immutable Git blob hash")
        raw = files[name].read_bytes()
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() +
                             bytes([0]) + raw).hexdigest() == git_hash,
                "public original Git object modified: " + name)
    license_bytes = (originals / "LICENSE").read_bytes()
    require(b"Redistribution and use in source and binary forms" in license_bytes,
            "unrecognized public source license")
    public = (source / "pubspec.yaml").read_text(encoding="utf-8")
    require("name: aivexus_external_" + package in public
            and "path: vendor/" + package in public,
            "generated adapter does not depend on vendored original")
    adapter = (source / "lib/aivexus_external.dart").read_text(encoding="utf-8")
    test = (source / "tool/self_test.dart").read_text(encoding="utf-8")
    require("package:" + package + "/" + package + ".dart" in adapter
            and "package:aivexus_external_" + package in test
            and "throw StateError(" in test
            and "dart:io" not in adapter
            and "dart:ffi" not in adapter
            and "dart:isolate" not in adapter,
            "functional adapter/test contract changed")
    require(data.get("upstream_files") == len(files), "incomplete source receipt")
    return {
        "schema": "aivexus.library.autonomous-public-dart-preflight.v1",
        "module": package, "source_commit": sha, "source_tag": data["source_tag"],
        "upstream_file_count": len(files), "payload_sha256": digest,
        "original_license_sha256": hashlib.sha256(license_bytes).hexdigest(),
        "source_materialized": True, "code_executed_by_preflight": False,
        "security_reviewed": False, "certification_authorized": False,
        "tested_on_host": [],
    }


def inspect_all(root: Path) -> dict:
    base = root / "sandbox/researcher_public_dart"
    found = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    require(all(name in PROFILES for name in found),
            "unrecognized Researcher-supplied package in sandbox")
    return {"schema": "aivexus.library.researcher-public-supply-summary.v1",
            "candidate_count": len(found),
            "candidates": [inspect(root, name) for name in found],
            "all_security_reviewed": False,
            "certification_authorized": False}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = inspect_all(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_count": result["candidate_count"],
                      "certification_authorized": False}))


if __name__ == "__main__":
    main()
