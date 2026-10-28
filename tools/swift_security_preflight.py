"""Separate, fail-closed Swift SBOM/OSV/security preflight for tested upstream.

Does NOT certify, sign a review, claim full source safety or mark security.reviewed.
The actual independent reviewer must assess the exposed privacy/capture surface.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from library_source_integrity import payload_tree_sha256
from swift_probe import read

OSV = "https://api.osv.dev/v1/querybatch"
GITHUB = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SCHEMA = "ai-orchestrator.swift-security-preflight.v1"
LIMIT = 1_048_576
SENSITIVE = {
    "global_stdout_stderr_capture": re.compile(r"\bdup2\s*\(\s*(?:STDOUT_FILENO|STDERR_FILENO)"),
    "process_environment_access": re.compile(r"\bProcessInfo\.processInfo\.environment\b"),
    "system_metrics_monitoring": re.compile(r"\bmetricsMonitor\.startMonitoring\s*\("),
}


class SwiftPreflightError(ValueError):
    pass


def fetch_license(repository: str, revision: str) -> tuple[str, bytes] | None:
    match = GITHUB.fullmatch(repository)
    if match is None or SHA40.fullmatch(revision) is None:
        raise SwiftPreflightError("unsafe pinned dependency repository")
    owner, repo = match.groups()
    for name in ("LICENSE", "license", "LICENSE.md", "license.md", "LICENSE.txt"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{revision}/{name}"
        request = urllib.request.Request(
            url, headers={"User-Agent": "AI-Orchestrator-Swift-Source-Review"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(LIMIT + 1)
            if 0 < len(data) <= LIMIT:
                return name, data
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise SwiftPreflightError("dependency license retrieval failed") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise SwiftPreflightError("dependency license retrieval failed") from exc
    return None


def query_osv(queries: list[dict]) -> list[dict]:
    data = json.dumps({"queries": queries}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        OSV,
        data=data,
        headers={"Content-Type": "application/json",
                 "User-Agent": "AI-Orchestrator-Swift-Source-Review"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise SwiftPreflightError("OSV scan unavailable: no negative security claim allowed") from exc
    rows = result.get("results") if isinstance(result, dict) else None
    if not isinstance(rows, list) or len(rows) != len(queries):
        raise SwiftPreflightError("OSV produced an incomplete querybatch")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("vulns", []), list):
            raise SwiftPreflightError("OSV response is malformed")
        if row.get("next_page_token"):
            raise SwiftPreflightError("OSV scan pagination incomplete")
    return rows


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pins(lock_path: Path) -> list[dict]:
    resolved = read(lock_path)
    pins = resolved.get("pins")
    if pins is None:
        pins = (resolved.get("object") or {}).get("pins")
    if not isinstance(pins, list) or not pins or len(pins) > 64:
        raise SwiftPreflightError("SwiftPM dependency inventory unpinned or missing")
    rows = []
    for pin in pins:
        if not isinstance(pin, dict):
            raise SwiftPreflightError("malformed SwiftPM dependency pin")
        repository = pin.get("location") or pin.get("repositoryURL")
        state = pin.get("state") or {}
        sha = state.get("revision")
        version = state.get("version")
        if (not isinstance(repository, str) or GITHUB.fullmatch(repository) is None
                or not isinstance(sha, str) or SHA40.fullmatch(sha) is None
                or not isinstance(version, str) or not version):
            raise SwiftPreflightError("unverified SwiftPM package pin")
        rows.append({"repository": repository, "commit": sha, "version": version})
    return sorted(rows, key=lambda x: (x["repository"], x["commit"]))


def _privacy_findings(source: Path) -> list[dict]:
    findings = []
    for file in sorted(source.rglob("*.swift")):
        if file.is_symlink() or not file.is_file() or file.stat().st_size > LIMIT:
            raise SwiftPreflightError("unsafe Swift source input")
        data = file.read_text(encoding="utf-8")
        for rule, pattern in SENSITIVE.items():
            if pattern.search(data):
                findings.append({
                    "rule": rule,
                    "source_path": file.relative_to(source).as_posix(),
                    "classification": "requires_independent_privacy_security_review",
                })
    return findings


def analyze(
    root: Path,
    *,
    scan: Callable[[list[dict]], list[dict]] = query_osv,
    license_lookup: Callable[[str, str], tuple[str, bytes] | None] = fetch_license,
    now: str | None = None,
) -> dict:
    for path in sorted((root / "intake").glob("*/*/manifest.json")):
        data = read(path)
        base = path.parent
        source = base / "payload"
        info = data.get("payload") or {}
        provenance = data.get("provenance") or {}
        if (data.get("status") != "tested"
                or "swift" not in data.get("languages", [])
                or info.get("type") != "upstream_reference"
                or not isinstance(info.get("sha256"), str)
                or data.get("validation", {}).get("tests_passed") is not True
                or (data.get("security") or {}).get("reviewed") is True):
            continue
        result_path = base / "evidence" / "security-preflight.json"
        if result_path.exists():
            before = read(result_path)
            if (before.get("schema") == SCHEMA
                    and before.get("payload_sha256") == info["sha256"]
                    and before.get("source_commit") == provenance.get("source_commit")
                    and before.get("reviewed") is False):
                continue
        if (source.is_symlink() or payload_tree_sha256(source) != info["sha256"]
                or not isinstance(provenance.get("source_commit"), str)
                or SHA40.fullmatch(provenance["source_commit"]) is None):
            raise SwiftPreflightError("source pin and source bytes differ")
        license_path = base / "provenance/LICENSE"
        upstream_license = source / "LICENSE"
        if not license_path.is_file() or not upstream_license.is_file():
            raise SwiftPreflightError("source license evidence missing")
        if license_path.read_bytes() != upstream_license.read_bytes():
            raise SwiftPreflightError("source license does not match immutable upstream")
        dependencies = _pins(source / "Package.resolved")
        license_reviews = []
        for dep in dependencies:
            license_entry = license_lookup(dep["repository"], dep["commit"])
            name, contents = license_entry if license_entry else ("", b"")
            is_mit = (b"permission is hereby granted" in contents.lower()
                      and b"mit" in contents[:200].lower())
            license_reviews.append({
                "repository": dep["repository"],
                "commit": dep["commit"],
                "license_path": name,
                "license_sha256": _sha(contents) if contents else None,
                "license_spdx": "MIT" if is_mit else None,
                "license_resolved": is_mit,
            })
        queries = [{"commit": provenance["source_commit"]}]
        for dep in dependencies:
            queries.append({"commit": dep["commit"]})
            normalized = GITHUB.fullmatch(dep["repository"])
            owner, repository = normalized.groups()
            queries.append({
                "package": {"ecosystem": "SwiftURL", "name": f"github.com/{owner}/{repository}"},
                "version": dep["version"],
            })
        results = scan(queries)
        if len(results) != len(queries):
            raise SwiftPreflightError("incomplete dependency OSV assessment")
        vuln_ids = sorted({
            str(v.get("id")) for row in results for v in row.get("vulns", [])
            if isinstance(v, dict) and isinstance(v.get("id"), str)
        })
        now_iso = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "library",
                    "name": data["id"],
                    "version": data["version"],
                    "hashes": [{"alg": "SHA-256", "content": info["sha256"]}],
                }
            },
            "components": [
                {
                    "type": "library",
                    "name": GITHUB.fullmatch(dep["repository"]).group(2),
                    "version": dep["version"],
                    "externalReferences": [
                        {"type": "vcs", "url": dep["repository"] + "/tree/" + dep["commit"]}
                    ],
                    "licenses": ([{"license": {"id": "MIT"}}] if license_reviews[i]["license_resolved"] else []),
                }
                for i, dep in enumerate(dependencies)
            ],
        }
        evidence_dir = base / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        sbom_path = evidence_dir / "sbom.cdx.json"
        sbom_data = (json.dumps(sbom, indent=2, sort_keys=True) + "\n").encode()
        sbom_path.write_bytes(sbom_data)
        findings = _privacy_findings(source)
        reasons = (
            ["known_dependency_vulnerabilities"] if vuln_ids else []
        ) + (
            ["dependency_license_review_missing"] if any(not x["license_resolved"] for x in license_reviews) else []
        ) + (
            ["sensitive_system_capture_requires_independent_review"] if findings else []
        )
        preflight = {
            "schema": SCHEMA,
            "asset_id": data["id"],
            "version": data["version"],
            "source_commit": provenance["source_commit"],
            "payload_sha256": info["sha256"],
            "generated_at": now_iso,
            "sbom_path": "evidence/sbom.cdx.json",
            "sbom_sha256": _sha(sbom_data),
            "dependency_licenses": license_reviews,
            "osv_queries": queries,
            "osv_results": results,
            "osv_vulnerability_ids": vuln_ids,
            "source_privacy_findings": findings,
            "review_required_reasons": reasons,
            "reviewed": False,
            "certification_authorized": False,
            "security_scope": "static source patterns and lockfile-pinned dependency OSV; not a full source audit",
        }
        result_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
        return {"scanned": 1, "asset_id": data["id"], "review_required": True,
                "known_osv_match_count": len(vuln_ids),
                "privacy_findings_count": len(findings),
                "dependency_license_unresolved": sum(not x["license_resolved"] for x in license_reviews)}
    return {"scanned": 0}


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    try:
        result = analyze(args.root)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, sort_keys=True))
    except (SwiftPreflightError, OSError, ValueError, UnicodeError) as exc:
        cli.exit(1, f"Swift security preflight failed closed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
