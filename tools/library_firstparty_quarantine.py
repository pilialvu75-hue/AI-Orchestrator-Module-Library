"""Bounded, safe first-party Library intake triage (not certification).

Only pre-existing immutable candidate manifests are changed. No upstream code
is fetched or executed and no module/catalog file is written. The ordinary
Library lifecycle transition enforces discovered -> quarantined.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from library_pipeline import AssetRef, PipelineError, transition_intake  # noqa: E402

SOURCE = "https://github.com/pilialvu75-hue/AI-Orchestrator-Core"
SOURCE_PROJECT = "pilialvu75-hue/AI-Orchestrator-Core"
VERSION = "0.1.0"
ALLOWED = (
    "ai.acceleration_backend.firstparty.ai-orchestrator-core",
    "ai.local_inference.firstparty.ai-orchestrator-core",
)
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def _read_manifest(root: Path, asset_id: str) -> dict | None:
    path = root / "intake" / asset_id / VERSION / "manifest.json"
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("untrusted first-party intake manifest is a symlink or non-file")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("intake manifest is not an object")
    provenance = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    if (manifest.get("id") != asset_id
            or manifest.get("version") != VERSION
            or manifest.get("status") not in (
                "discovered", "quarantined", "normalized", "tested"
            )
            or not isinstance(provenance, dict)
            or provenance.get("source_repository") != SOURCE
            or provenance.get("source_project_id") != SOURCE_PROJECT
            or provenance.get("origin") != "researcher"
            or not isinstance(provenance.get("source_commit"), str)
            or not COMMIT.fullmatch(provenance["source_commit"])
            or not isinstance(payload, dict)
            or payload.get("type") != "upstream_reference"
            or payload.get("upstream_repository") != SOURCE
            or payload.get("upstream_commit") != provenance["source_commit"]):
        raise ValueError(f"{asset_id}: unrecognized first-party intake identity/provenance")
    return manifest


def _certification_blockers(manifest: dict) -> list[str]:
    blockers = []
    provenance = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    validation = manifest.get("validation") or {}
    security = manifest.get("security") or {}
    if provenance.get("license") in (None, "", "NOASSERTION") or not provenance.get("license_file"):
        blockers.append("LICENSE_EVIDENCE_MISSING")
    if payload.get("type") == "upstream_reference" or not payload.get("path") or not payload.get("sha256"):
        blockers.append("LOCAL_HASHED_PAYLOAD_MISSING")
    if validation.get("tests_passed") is not True or not validation.get("test_report"):
        blockers.append("REPRODUCIBLE_TEST_EVIDENCE_MISSING")
    if security.get("reviewed") is not True or not security.get("review_report"):
        blockers.append("SECURITY_REVIEW_EVIDENCE_MISSING")
    return blockers


def triage(*, root: Path = ROOT, apply: bool = False) -> dict:
    items = []
    for asset_id in ALLOWED:
        manifest = _read_manifest(root, asset_id)
        if manifest is None:
            items.append({"asset_id": asset_id, "result": "NOT_IN_INTAKE",
                          "certified": False, "blockers": ["CANDIDATE_NOT_PRESENT"]})
            continue
        status = manifest["status"]
        blockers = _certification_blockers(manifest)
        result = "NO_MUTATION"
        if status == "discovered":
            result = "ELIGIBLE_FOR_QUARANTINE"
            if apply:
                # Never substitute a direct status edit for the lifecycle API.
                manifest = transition_intake(
                    root, AssetRef(asset_id=asset_id, version=VERSION),
                    "quarantined",
                )
                if manifest.get("status") != "quarantined":
                    raise ValueError("Library lifecycle did not quarantine candidate")
                result = "QUARANTINED"
        items.append({
            "asset_id": asset_id, "version": VERSION,
            "status": manifest["status"], "result": result,
            "certified": False, "blockers": blockers,
        })
    return {
        "schema_version": 1,
        "profile": "bounded-firstparty-quarantine-v1",
        "read_only": not apply,
        "certified_count_added": 0,
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="use the existing Library discovered->quarantined transition")
    args = parser.parse_args(argv)
    try:
        result = triage(apply=args.apply)
    except (OSError, ValueError, PipelineError) as exc:
        print(f"first-party quarantine triage refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
