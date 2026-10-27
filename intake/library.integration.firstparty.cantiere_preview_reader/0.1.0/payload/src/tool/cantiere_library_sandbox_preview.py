#!/usr/bin/env python3
"""Isolated Cantiere proof: import a *real* Library preview with integrity checks.

This is not the certified Module Library production reader and not Flutter
auto-installation. No package is executed automatically; --probe explicitly
enables one allowlisted, synthetic Node.js smoke test in an ephemeral directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

LIBRARY_BASE = (
    "https://raw.githubusercontent.com/"
    "pilialvu75-hue/AI-Orchestrator-Module-Library/main"
)
INDEX_PATH = "packages/experimental-index.json"
INDEX_SCHEMA = "ai-orchestrator.library-experimental-index.v1"
PACKAGE_SCHEMA = "ai-orchestrator.library-module-package.v1"
ENVELOPE_SCHEMA = "ai-orchestrator.library-module-package-envelope.v1"
POLICY = "internal-isolated-evaluation-only"
ALLOWLISTED_PROBE = "release.update_manager.firstparty.mia@0.1.0"
MAX_RESPONSE = 4 * 1024 * 1024
MAX_PAYLOAD = 1024 * 1024
_SHA = re.compile(r"[a-f0-9]{64}\Z")


class PreviewError(ValueError):
    pass


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise PreviewError(message)


def _safe_path(value: object) -> str:
    _ensure(isinstance(value, str) and value, "missing package file path")
    _ensure(len(value) <= 256 and "\\" not in value and "\x00" not in value,
            "unsafe package file path")
    path = PurePosixPath(value)
    _ensure(not path.is_absolute() and not value.startswith("~") and
            not any(part in ("", ".", "..") for part in value.split("/")) and
            ":" not in value and not any(part in (".git", "build", "node_modules")
                                        for part in path.parts),
            "unsafe package file path")
    return value


def _download_json(path: str) -> dict:
    safe = _safe_path(path)
    url = LIBRARY_BASE + "/" + safe
    req = urllib.request.Request(url, headers={"User-Agent": "aivexus-cantiere-preview/1"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(MAX_RESPONSE + 1)
    _ensure(len(data) <= MAX_RESPONSE, "Library response too large")
    result = json.loads(data)
    _ensure(isinstance(result, dict), "Library response must be an object")
    return result


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_preview(index: dict, envelope: dict, pin: str) -> dict[str, bytes]:
    """Check index-authorized identity, package bytes, policy and every file."""
    _ensure(index.get("schema") == INDEX_SCHEMA and
            index.get("policy") == POLICY and index.get("certified") is False,
            "not the expected experimental index")
    rows = index.get("packages")
    _ensure(isinstance(rows, list), "experimental index packages invalid")
    matches = [row for row in rows if isinstance(row, dict) and row.get("pin") == pin]
    _ensure(len(matches) == 1, "pin is not uniquely indexed for sandbox use")
    row = matches[0]
    expected_path = "packages/experimental/" + pin.replace("@", "/") + "/package.json"
    _ensure(_safe_path(row.get("path")) == expected_path and
            row.get("tier") == "sandbox_preview" and
            row.get("production_approved") is False,
            "experimental index entry is not sandbox-safe")
    expected_sha = row.get("package_sha256")
    _ensure(isinstance(expected_sha, str) and _SHA.fullmatch(expected_sha),
            "missing trusted package SHA-256")
    _ensure(envelope.get("schema") == ENVELOPE_SCHEMA and
            isinstance(envelope.get("package"), dict),
            "unsupported package envelope")
    package = envelope["package"]
    actual_sha = _canonical_sha256(package)
    _ensure(actual_sha == expected_sha == envelope.get("package_sha256"),
            "package digest mismatch")
    _ensure(package.get("schema") == PACKAGE_SCHEMA and
            package.get("pin") == pin and
            package.get("asset_id") + "@" + package.get("version") == pin,
            "package identity mismatch")
    _ensure(package.get("tier") == "sandbox_preview" and
            package.get("status") == "tested" and
            package.get("certified") is False and
            package.get("availability") == "experimental" and
            package.get("usage_policy") == POLICY and
            package.get("review", {}).get("production_approved") is False,
            "package is not restricted to sandbox evaluation")
    _ensure("linux" in package.get("targets", []), "Linux was not validated")
    requirements = package.get("requirements")
    _ensure(isinstance(requirements, list) and
            any(isinstance(r, dict) and r.get("kind") == "distributionRestriction"
                and r.get("required") is True for r in requirements),
            "missing mandatory sandbox-use restriction")
    _ensure(any(isinstance(r, dict) and r.get("kind") == "dependency"
                and "Node.js" in r.get("description", "") for r in requirements),
            "Node.js runtime dependency not declared")
    integrity = package.get("integrity") or {}
    expected_payload = integrity.get("payload_sha256")
    _ensure(isinstance(expected_payload, str) and _SHA.fullmatch(expected_payload),
            "source tree digest missing")
    files = package.get("files")
    _ensure(isinstance(files, list) and 1 <= len(files) <= 64,
            "invalid preview file count")
    output: dict[str, bytes] = {}
    total = 0
    for item in files:
        _ensure(isinstance(item, dict), "invalid source file")
        target = _safe_path(item.get("target_path"))
        _safe_path(item.get("source_path"))
        _ensure(target not in output, "duplicate module file path")
        source = item.get("content")
        _ensure(isinstance(source, str), "module file content must be text")
        data = source.encode("utf-8")
        total += len(data)
        _ensure(len(data) <= MAX_PAYLOAD and total <= MAX_PAYLOAD,
                "preview source bundle exceeds limit")
        output[target] = data
    digest = hashlib.sha256()
    for target, content in sorted(output.items()):
        rel = target.encode("utf-8")
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(hashlib.sha256(content).digest())
    _ensure(digest.hexdigest() == expected_payload,
            "local source tree digest differs from immutable package claim")
    return output


def _write_preview(root: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _run_allowlisted_probe(root: Path, pin: str) -> str:
    _ensure(pin == ALLOWLISTED_PROBE, "execution not approved for this preview pin")
    # This is a smoke test of public APIs, not an OTA deployment or privileged
    # updater. Node permissions restrict filesystem writes/process spawning.
    probe = r"""
import crypto from 'node:crypto';
import {AutoUpdateEngine, ModuleLoader} from './services/mia-ota-manager/src/otaManager.js';
const engine = new AutoUpdateEngine();
const data = Buffer.from('Cantiere isolated integration proof');
const hash = crypto.createHash('sha256').update(data).digest('hex');
if (!engine.verifyIntegrity(data, hash)) throw Error('valid digest refused');
if (engine.verifyIntegrity(Buffer.from('tampered'), hash)) throw Error('tamper accepted');
if (engine.checkUpdates('1.0.0', [{version:'1.1.0'}])?.version !== '1.1.0')
  throw Error('update comparison failed');
const loader = new ModuleLoader();
loader.loadModule({name:'cantiere-preview', version:'0.1.0', dependencies:[]});
if (!loader.modules.has('cantiere-preview')) throw Error('module load failed');
console.log('PASS: imported and executed real Library experimental Mia OTA API');
"""
    result = subprocess.run(
        ["node", "--permission", f"--allow-fs-read={root}",
         "--input-type=module", "--eval", probe],
        cwd=root,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
             "HOME": str(root)},
        text=True, capture_output=True, timeout=20, check=False,
    )
    _ensure(result.returncode == 0,
            "sandbox Node probe failed: " + (result.stderr or result.stdout)[-700:])
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", default=ALLOWLISTED_PROBE)
    parser.add_argument("--probe", action="store_true",
                        help="execute allowlisted public API smoke in temporary sandbox")
    args = parser.parse_args()
    try:
        index = _download_json(INDEX_PATH)
        item = next((x for x in index.get("packages", []) if x.get("pin") == args.pin), None)
        _ensure(item is not None, "module pin not in experimental index")
        package = _download_json(_safe_path(item.get("path")))
        files = verify_preview(index, package, args.pin)
        print(f"VERIFIED: {args.pin} ({len(files)} real source files)")
        with tempfile.TemporaryDirectory(prefix="aivexus-library-preview-") as temp:
            root = Path(temp)
            _write_preview(root, files)
            if args.probe:
                print(_run_allowlisted_probe(root, args.pin))
        print("PASS: ephemeral preview cleaned; nothing installed in Flutter")
        return 0
    except (PreviewError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
