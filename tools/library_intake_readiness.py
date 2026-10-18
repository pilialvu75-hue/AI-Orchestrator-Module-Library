"""Deterministic, read-only intake readiness inventory (never a certification).

The report bridges the gap between Researcher candidates and the Library's
authoritative certified catalog. It reports missing *evidence*, not trust, and
does not execute upstream code, mutate intake or set any certification gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ASSET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}\Z")
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?\Z")
ALLOWED_STATES = {"discovered", "quarantined", "normalized", "tested"}
PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MAX_INTAKE_ASSETS = 500
MAX_MANIFEST_BYTES = 1024 * 1024

REMEDIATION = {
    "PINNED_SOURCE_MISSING": "Provide an immutable upstream repository and full source commit.",
    "LICENSE_EVIDENCE_MISSING": "Resolve the upstream license and supply its attributable license file.",
    "SOURCE_SNAPSHOT_MISSING": "Materialize immutable source bytes from the pinned commit in an isolated evidence workflow.",
    "REPRODUCIBLE_TEST_EVIDENCE_MISSING": "Run isolated reproducible tests on the pinned source and attach a bound report.",
    "SECURITY_REVIEW_EVIDENCE_MISSING": "Attach an independently generated security report and SBOM bound to the pinned source.",
    "KNOWN_VULNERABILITIES_PRESENT": "Resolve known vulnerabilities before certification.",
    "RESTRICTED_LICENSE_REVIEW_REQUIRED": "Obtain an explicit license-policy decision; automatic promotion is forbidden.",
}


class ReadinessError(ValueError):
    pass


def _object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ReadinessError(f"missing or symlinked metadata file: {path.name}")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ReadinessError(f"metadata file exceeds size limit: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"invalid JSON metadata: {path.name}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"metadata root must be an object: {path.name}")
    return value


def _safe_evidence_file(base: Path, value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return False
    candidate = base / path
    if candidate.is_symlink() or not candidate.is_file():
        return False
    return base.resolve() in candidate.resolve().parents and candidate.stat().st_size > 0


def _has_source_snapshot(base: Path, payload: dict) -> bool:
    if payload.get("type") == "upstream_reference":
        directory = base / "payload"
        if not directory.is_dir() or directory.is_symlink():
            return False
        for file in directory.rglob("*"):
            if file.is_symlink():
                raise ReadinessError("source snapshot contains a symlink")
            if file.is_file() and file.stat().st_size:
                return True
        return False
    raw = payload.get("path")
    return _safe_evidence_file(base, raw) if payload.get("type") == "archive" else bool(
        isinstance(raw, str) and raw and (base / raw).is_dir()
        and not (base / raw).is_symlink()
        and ".." not in Path(raw).parts and not Path(raw).is_absolute()
    )


def _license_restricted(value: str) -> bool:
    v = value.upper().strip()
    return "AGPL" in v or "SSPL" in v or bool(re.search(r"(^|[ (|])GPL-[0-9]", v))


def _candidate(base: Path) -> dict:
    if base.is_symlink() or base.parent.is_symlink():
        raise ReadinessError("intake directory is a symlink")
    asset_id, version = base.parent.name, base.name
    if not ASSET_ID.fullmatch(asset_id) or not SEMVER.fullmatch(version):
        raise ReadinessError("unsafe intake asset ID or version")
    manifest = _object(base / "manifest.json")
    if (manifest.get("id") != asset_id or manifest.get("version") != version
            or manifest.get("status") not in ALLOWED_STATES):
        raise ReadinessError("intake identity or lifecycle state mismatch")
    provenance = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    validation = manifest.get("validation") or {}
    security = manifest.get("security") or {}
    capabilities = manifest.get("capabilities")
    if (not all(isinstance(x, dict) for x in
                (provenance, payload, validation, security))
            or not isinstance(capabilities, list)
            or not capabilities
            or not all(isinstance(x, str) and x for x in capabilities)):
        raise ReadinessError("invalid candidate evidence or capabilities")
    blockers: list[str] = []
    commit = provenance.get("source_commit")
    repository = provenance.get("source_repository")
    if (not isinstance(commit, str) or not SHA40.fullmatch(commit)
            or not isinstance(repository, str) or not repository.startswith("https://github.com/")):
        blockers.append("PINNED_SOURCE_MISSING")
    license_name = str(provenance.get("license") or "")
    if (license_name.upper() in {"", "NOASSERTION", "UNKNOWN", "LICENSE_UNKNOWN"}
            or not _safe_evidence_file(base, provenance.get("license_file"))):
        blockers.append("LICENSE_EVIDENCE_MISSING")
    if _license_restricted(license_name):
        blockers.append("RESTRICTED_LICENSE_REVIEW_REQUIRED")
    if not _has_source_snapshot(base, payload):
        blockers.append("SOURCE_SNAPSHOT_MISSING")
    if (validation.get("tests_passed") is not True
            or not _safe_evidence_file(base, validation.get("test_report"))
            or not isinstance(validation.get("validated_on"), list)
            or not validation["validated_on"]):
        blockers.append("REPRODUCIBLE_TEST_EVIDENCE_MISSING")
    if (security.get("reviewed") is not True
            or not _safe_evidence_file(base, security.get("review_report"))
            or not _safe_evidence_file(base, security.get("sbom"))):
        blockers.append("SECURITY_REVIEW_EVIDENCE_MISSING")
    vulns = security.get("known_vulnerabilities")
    if type(vulns) is int and vulns > 0:
        blockers.append("KNOWN_VULNERABILITIES_PRESENT")
    # Merely having local report files cannot authenticate source execution.
    # This read-only inventory never labels an asset "certification-ready".
    return {
        "asset_id": asset_id,
        "version": version,
        "status": manifest["status"],
        "capabilities": sorted(set(capabilities)),
        "source_repository": repository if isinstance(repository, str) else None,
        "source_commit": commit if isinstance(commit, str) and SHA40.fullmatch(commit) else None,
        "blockers": blockers,
        "next_actions": [REMEDIATION[code] for code in blockers],
        "independent_certification_authorized": False,
    }


def build_report(root: Path = ROOT) -> dict:
    intake_root = root / "intake"
    if intake_root.is_symlink() or not intake_root.is_dir():
        raise ReadinessError("intake directory is missing or symlinked")
    manifests = sorted(intake_root.glob("*/*/manifest.json"))
    if len(manifests) > MAX_INTAKE_ASSETS:
        raise ReadinessError("intake report exceeds bounded candidate limit")
    assets = [_candidate(path.parent) for path in manifests]
    if len({(x["asset_id"], x["version"]) for x in assets}) != len(assets):
        raise ReadinessError("duplicate intake identity")
    needs = _object(root / "catalog/needs.json")
    catalog = _object(root / "catalog/index.json")
    if not isinstance(needs.get("items"), list) or not isinstance(catalog.get("assets"), list):
        raise ReadinessError("invalid canonical Library needs or catalog")
    certified = [x for x in catalog["assets"] if isinstance(x, dict) and x.get("status") == "certified"]
    coverage = []
    seen_capabilities = set()
    for need in needs["items"]:
        if not isinstance(need, dict):
            raise ReadinessError("invalid Library needs entry")
        capability = need.get("capability_id")
        desired = need.get("desired_candidates")
        targets = need.get("targets")
        if (not isinstance(capability, str) or not capability or capability in seen_capabilities
                or type(desired) is not int or desired < 1
                or not isinstance(targets, list)
                or not all(isinstance(t, str) and t for t in targets)):
            raise ReadinessError("invalid or duplicate Library need")
        seen_capabilities.add(capability)
        certified_rows = [a for a in certified if capability in (a.get("capabilities") or [])]
        candidate_rows = [a for a in assets if capability in a["capabilities"]]
        per_target = [
            {"target": t, "certified_count": sum(
                t in (a.get("platforms") or []) for a in certified_rows)}
            for t in sorted(set(targets))
        ]
        coverage.append({
            "capability_id": capability,
            "title": need.get("title"),
            "priority": need.get("priority"),
            "desired_candidates": desired,
            "certified_count": len(certified_rows),
            "remaining_to_goal": max(0, desired - len(certified_rows)),
            "intake_candidates": len(candidate_rows),
            "blocked_candidates": sum(bool(x["blockers"]) for x in candidate_rows),
            "certified_by_target": per_target,
        })
    coverage.sort(key=lambda x: (
        PRIORITY.get(str(x["priority"]), 9), -x["remaining_to_goal"],
        -x["intake_candidates"], x["capability_id"],
    ))
    blocker_counts = Counter(code for item in assets for code in item["blockers"])
    return {
        "schema_version": 1,
        "report_type": "read_only_evidence_gaps_not_certification",
        "summary": {
            "certified_catalog_entries": len(certified),
            "intake_candidates": len(assets),
            "blocked_intake_candidates": sum(bool(a["blockers"]) for a in assets),
            "ready_for_automatic_certification": 0,
            "blocker_counts": dict(sorted(blocker_counts.items())),
        },
        "coverage": coverage,
        "candidates": assets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic Library intake evidence-gap inventory")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.root)
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        print(json.dumps(report["summary"], sort_keys=True))
        return 0
    except (ReadinessError, OSError) as exc:
        print(f"Library readiness inventory refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
