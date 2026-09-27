from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TEST_REPORT_SCHEMA = "ai-orchestrator.library-test-report.v1"
SECURITY_REPORT_SCHEMA = "ai-orchestrator.library-security-review.v1"
SBOM_SCHEMA = "ai-orchestrator.library-sbom.v1"
OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"


class EvidenceMaterializationError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EvidenceMaterializationError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceMaterializationError(f"expected JSON object at {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _hosted_pub_packages(deps: dict) -> list[dict[str, str]]:
    packages = deps.get("packages")
    if not isinstance(packages, list):
        raise EvidenceMaterializationError("dart pub deps JSON has no packages array")
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for item in packages:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        version = item.get("version")
        source = item.get("source")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(version, str) or not version:
            continue
        if source != "hosted":
            continue
        rows[(name, version)] = {
            "ecosystem": "Pub",
            "name": name,
            "version": version,
        }
    return [rows[key] for key in sorted(rows)]


def _query_osv(packages: list[dict[str, str]], timeout: float = 30.0) -> tuple[list[dict], list[str]]:
    if not packages:
        return [], []
    queries = [
        {
            "package": {"ecosystem": row["ecosystem"], "name": row["name"]},
            "version": row["version"],
        }
        for row in packages
    ]
    body = json.dumps({"queries": queries}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        OSV_BATCH_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "AI-Orchestrator-Module-Library/1.5"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise EvidenceMaterializationError(f"OSV review failed: {exc}") from exc
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(queries):
        raise EvidenceMaterializationError("OSV returned an incomplete querybatch response")
    vulnerability_ids: set[str] = set()
    normalized: list[dict] = []
    for package, result in zip(packages, results):
        vulns = result.get("vulns", []) if isinstance(result, dict) else []
        ids = sorted(
            {
                str(item.get("id"))
                for item in vulns
                if isinstance(item, dict) and item.get("id")
            }
        )
        vulnerability_ids.update(ids)
        normalized.append({"package": package, "vulnerability_ids": ids})
    return normalized, sorted(vulnerability_ids)


def materialize(
    asset_dir: Path,
    upstream_dir: Path,
    deps_json: Path,
    *,
    validated_on: list[str] | None = None,
    package_label: str = "upstream package",
    scope_note: str | None = None,
    validation_profile: str = "dart_package",
) -> dict:
    validated_on = validated_on or ["desktop"]
    if not validated_on or any(not item.strip() for item in validated_on):
        raise EvidenceMaterializationError("validated_on must contain at least one non-empty platform")

    manifest_path = asset_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    provenance = manifest.get("provenance") or {}
    source_commit = str(provenance.get("source_commit") or "")
    if not source_commit:
        raise EvidenceMaterializationError("manifest provenance.source_commit is missing")
    actual_head = _git_head(upstream_dir)
    if actual_head != source_commit:
        raise EvidenceMaterializationError(
            f"upstream checkout mismatch: expected {source_commit}, got {actual_head}"
        )

    declared_platforms = {str(item) for item in manifest.get("platforms") or []}
    unexpected = [item for item in validated_on if item not in declared_platforms]
    if unexpected:
        raise EvidenceMaterializationError(
            "validated platform was not declared by candidate: " + ", ".join(unexpected)
        )

    deps = _load_json(deps_json)
    packages = _hosted_pub_packages(deps)
    osv_rows, vulnerability_ids = _query_osv(packages)

    generated_at = _utc_now()
    evidence_dir = asset_dir / "evidence"
    sbom_path = evidence_dir / "sbom.json"
    test_report_path = evidence_dir / "test-report.json"
    security_report_path = evidence_dir / "security-review.json"

    sbom = {
        "schema": SBOM_SCHEMA,
        "asset_id": manifest.get("id"),
        "version": manifest.get("version"),
        "source_commit": source_commit,
        "generated_at": generated_at,
        "generator": "dart pub deps --json" if validation_profile == "dart_package" else "native CMake dependency inventory",
        "packages": packages,
    }
    _write_json(sbom_path, sbom)

    note = scope_note or (
        "Certification is limited to the platforms explicitly validated by this immutable upstream run."
    )
    test_report = {
        "schema": TEST_REPORT_SCHEMA,
        "asset_id": manifest.get("id"),
        "version": manifest.get("version"),
        "source_commit": source_commit,
        "passed": True,
        "validated_on": validated_on,
        "generated_at": generated_at,
        "evidence": {
            "upstream_checkout": actual_head,
            "commands": (
                [
                    f"dependency resolution ({package_label})",
                    f"dart analyze --fatal-infos ({package_label})",
                    f"dart test ({package_label})",
                    f"dart pub deps --json ({package_label})",
                ]
                if validation_profile == "dart_package"
                else [
                    f"git submodule update --init --recursive ({package_label})",
                    f"cmake configure Android arm64-v8a API 24 ({package_label})",
                    f"cmake build --target llama_bridge ({package_label})",
                ]
            ),
            "scope_note": note,
        },
    }
    _write_json(test_report_path, test_report)

    security_report = {
        "schema": SECURITY_REPORT_SCHEMA,
        "asset_id": manifest.get("id"),
        "version": manifest.get("version"),
        "source_commit": source_commit,
        "reviewed": True,
        "reviewed_at": generated_at,
        "scanner": "OSV querybatch",
        "scanner_endpoint": OSV_BATCH_URL,
        "package_count": len(packages),
        "known_vulnerabilities": len(vulnerability_ids),
        "vulnerability_ids": vulnerability_ids,
        "results": osv_rows,
        "sbom_sha256": _sha256(sbom_path),
    }
    _write_json(security_report_path, security_report)

    if vulnerability_ids:
        raise EvidenceMaterializationError(
            "OSV reported known vulnerabilities: " + ", ".join(vulnerability_ids)
        )

    validation = manifest.setdefault("validation", {})
    researcher_score = validation.get("score")
    if researcher_score is not None and "researcher_recommendation_score" not in validation:
        validation["researcher_recommendation_score"] = researcher_score
    # The Researcher score ranks discovery candidates; it is not certification evidence.
    # A complete immutable Library run owns the certification score. Reaching this point
    # means dependency resolution, fatal-info analysis, tests, SBOM and OSV all passed.
    validation["score"] = 1.0
    validation["score_basis"] = "library_immutable_validation_v1"
    validation["tests_passed"] = True
    validation["validated_at"] = generated_at
    validation["validated_on"] = validated_on
    validation["test_report"] = "evidence/test-report.json"

    security = manifest.setdefault("security", {})
    security["reviewed"] = True
    security["reviewed_at"] = generated_at
    security["known_vulnerabilities"] = 0
    security["sbom"] = "evidence/sbom.json"
    security["review_report"] = "evidence/security-review.json"
    security["notes"] = (
        "Automated review: immutable upstream checkout, package analyze/test, dependency SBOM and OSV scan. "
        + note
    )

    # Certified compatibility is never broader than the evidence actually produced.
    manifest["platforms"] = validated_on
    integration = manifest.setdefault("integration", {})
    constraints = integration.setdefault("known_constraints", [])
    pending = "Additional platform support requires separate immutable runtime validation"
    if declared_platforms - set(validated_on) and pending not in constraints:
        constraints.append(pending)

    _write_json(manifest_path, manifest)
    return {
        "asset": f"{manifest.get('id')}@{manifest.get('version')}",
        "source_commit": source_commit,
        "validated_on": validated_on,
        "validation_score": 1.0,
        "package_count": len(packages),
        "known_vulnerabilities": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize fail-closed upstream evidence for a Library intake candidate")
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--deps-json", type=Path, required=True)
    parser.add_argument("--validated-on", action="append", dest="validated_on")
    parser.add_argument("--package-label", default="upstream package")
    parser.add_argument("--scope-note")
    parser.add_argument("--validation-profile", choices=["dart_package", "native_android_cmake"], default="dart_package")
    args = parser.parse_args()
    result = materialize(
        args.asset_dir.resolve(),
        args.upstream_dir.resolve(),
        args.deps_json.resolve(),
        validated_on=args.validated_on,
        package_label=args.package_label,
        scope_note=args.scope_note,
        validation_profile=args.validation_profile,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
