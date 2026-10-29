from __future__ import annotations

import argparse
import hashlib
import json
import sys
from functools import cmp_to_key
from pathlib import Path

from library_history import AssetRef, compare_semver, load_history, summarize_history

ROOT = Path(__file__).resolve().parents[1]
EFFORT_ORDER = {"trivial": 0, "low": 1, "medium": 2, "high": 3}
EFFORT_SCORE = {"trivial": 1.0, "low": 0.8, "medium": 0.5, "high": 0.2}
SELECTABLE_AVAILABILITY = {"active", "deprecated"}
POLICY_ID = "balanced-v1"
POLICY_WEIGHTS = {
    "validation": 0.45,
    "integration_effort": 0.25,
    "operational_reliability": 0.20,
    "evidence_confidence": 0.10,
}


class ResolverError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ResolverError(message)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ResolverError(f"invalid JSON at {path}: {exc}") from exc


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    require(root.is_dir(), f"module directory does not exist: {root}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        require(not path.is_symlink(), f"certified module tree contains symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content_hash = bytes.fromhex(sha256_file(path))
        digest.update(content_hash)
    return digest.hexdigest()


def safe_repo_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    resolved_root = root.resolve()
    require(path == resolved_root or resolved_root in path.parents, f"catalog path escapes repository: {relative}")
    return path


def availability(entry: dict) -> str:
    value = str(entry.get("availability", "active"))
    require(value in {"active", "deprecated", "revoked"}, f"invalid availability {value}")
    return value


def catalog(root: Path) -> dict:
    value = load_json(root / "catalog" / "index.json")
    require(isinstance(value.get("assets"), list), "catalog.assets must be an array")
    return value


def contracts(root: Path) -> dict:
    value = load_json(root / "contracts" / "index.json")
    require(isinstance(value.get("contracts"), list), "contracts.contracts must be an array")
    return value


def needs(root: Path) -> dict:
    value = load_json(root / "catalog" / "needs.json")
    require(isinstance(value.get("items"), list), "needs.items must be an array")
    return value


def contract_map(root: Path) -> dict[str, dict]:
    return {
        str(item["contract_id"]): item
        for item in contracts(root)["contracts"]
        if isinstance(item, dict) and item.get("contract_id")
    }


def normalize_score(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def ranking_components(manifest: dict, observation_summary: dict) -> dict:
    validation_score = normalize_score((manifest.get("validation") or {}).get("score"))
    effort = str((manifest.get("integration") or {}).get("estimated_effort", "high"))
    effort_score = EFFORT_SCORE.get(effort, 0.0)

    successes = int(observation_summary.get("successful_integrations") or 0)
    failures = int(observation_summary.get("failed_integrations") or 0)
    attempts = max(0, successes + failures)
    reliability = (successes + 1) / (attempts + 2)
    evidence_confidence = min(attempts / 5.0, 1.0)

    total = (
        POLICY_WEIGHTS["validation"] * validation_score
        + POLICY_WEIGHTS["integration_effort"] * effort_score
        + POLICY_WEIGHTS["operational_reliability"] * reliability
        + POLICY_WEIGHTS["evidence_confidence"] * evidence_confidence
    )
    return {
        "policy": POLICY_ID,
        "score": round(total, 6),
        "components": {
            "validation": round(validation_score, 6),
            "integration_effort": round(effort_score, 6),
            "operational_reliability": round(reliability, 6),
            "evidence_confidence": round(evidence_confidence, 6),
        },
        "weights": dict(POLICY_WEIGHTS),
        "evidence": {
            "successful_integrations": successes,
            "failed_integrations": failures,
            "attempts": attempts,
            "estimated_effort": effort,
        },
        "note": "Ranking compares Library candidates only; it does not decide whether reuse is cheaper than fresh implementation.",
    }


def manifest_for_entry(root: Path, entry: dict) -> tuple[Path, dict]:
    relative = entry.get("manifest")
    require(isinstance(relative, str) and relative, "catalog entry is missing manifest path")
    path = safe_repo_path(root, relative)
    require(path.is_file(), f"catalog manifest does not exist: {relative}")
    manifest = load_json(path)
    require(manifest.get("id") == entry.get("id"), f"manifest id mismatch for {relative}")
    require(manifest.get("version") == entry.get("version"), f"manifest version mismatch for {relative}")
    return path, manifest


def contract_details(registry: dict[str, dict], contract_ids: list[str]) -> list[dict]:
    result = []
    for contract_id in sorted(set(contract_ids)):
        metadata = registry.get(contract_id)
        result.append(
            {
                "contract_id": contract_id,
                "status": None if metadata is None else metadata.get("status"),
                "contract_version": None if metadata is None else metadata.get("contract_version"),
                "known": metadata is not None,
            }
        )
    return result


def asset_record(root: Path, entry: dict, registry: dict[str, dict] | None = None) -> dict:
    registry = registry or contract_map(root)
    manifest_path, manifest = manifest_for_entry(root, entry)
    ref = AssetRef(str(entry["id"]), str(entry["version"]))
    observations = summarize_history(load_history(root, ref))
    contract_ids = [str(value) for value in entry.get("contracts", [])]
    contract_info = contract_details(registry, contract_ids)
    warnings = []
    unknown = [item["contract_id"] for item in contract_info if not item["known"]]
    draft = [item["contract_id"] for item in contract_info if item["known"] and item["status"] != "stable"]
    if unknown:
        warnings.append("unknown contracts: " + ", ".join(unknown))
    if draft:
        warnings.append("non-stable contracts: " + ", ".join(draft))
    payload = manifest.get("payload") or {}
    if (payload.get("type") == "upstream_reference"
            and (payload.get("path") is None or payload.get("sha256") is None)):
        warnings.append(
            "reference-only upstream asset: original source bytes not materialized; "
            "not exportable or selectable as a ready module"
        )

    module_dir = manifest_path.parent
    return {
        "id": entry["id"],
        "version": entry["version"],
        "kind": entry.get("kind", manifest.get("kind")),
        "status": entry.get("status"),
        "availability": availability(entry),
        "description": manifest.get("description"),
        "capabilities": list(entry.get("capabilities") or manifest.get("capabilities") or []),
        "platforms": list(entry.get("platforms") or manifest.get("platforms") or []),
        "contracts": contract_info,
        "dependencies": manifest.get("dependencies", []),
        "provenance": manifest.get("provenance", {}),
        "validation": manifest.get("validation", {}),
        "security": manifest.get("security", {}),
        "integration": manifest.get("integration", {}),
        "connector": manifest.get("connector", {}),
        "payload": manifest.get("payload", {}),
        "observations": observations,
        "ranking": ranking_components(manifest, observations),
        "integrity": {
            "manifest_sha256": sha256_file(manifest_path),
            "module_tree_sha256": tree_sha256(module_dir),
        },
        "paths": {
            "manifest": str(manifest_path.relative_to(root).as_posix()),
            "module": str(module_dir.relative_to(root).as_posix()),
        },
        "warnings": warnings,
    }


def candidate_matches(
    record: dict,
    *,
    capability: str,
    contract_id: str | None,
    target: str | None,
    kind: str | None,
    max_effort: str | None,
    include_deprecated: bool,
    include_adaptable: bool,
    require_stable_contract: bool,
) -> bool:
    status = record["status"]
    payload = record.get("payload") or {}
    # Preserve legacy catalog/provenance for recovery and auditing, but never
    # recommend an upstream URL without materialized, pinned source as a
    # certified module ready for Cantiere consumption.
    if status == "certified" and payload.get("type") == "upstream_reference":
        if (payload.get("path") != "payload"
                or not isinstance(payload.get("sha256"), str)
                or len(payload["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in payload["sha256"])):
            return False
    if status != "certified":
        if not include_adaptable or status != "tested":
            return False
        integration = record.get("integration") or {}
        security = record.get("security") or {}
        validation = record.get("validation") or {}
        provenance = record.get("provenance") or {}
        # Adaptable candidates are visible for Cantiere transformation only. They are
        # never equivalent to certified assets and must still have concrete evidence.
        if not integration.get("adaptation_allowed"):
            return False
        if not validation.get("tests_passed") or normalize_score(validation.get("score")) < 0.60:
            return False
        if not security.get("reviewed") or int(security.get("known_vulnerabilities") or 0) != 0:
            return False
        if not provenance.get("source_repository") or not provenance.get("source_commit"):
            return False
    current_availability = record["availability"]
    if current_availability == "revoked":
        return False
    if current_availability == "deprecated" and not include_deprecated:
        return False
    if current_availability not in SELECTABLE_AVAILABILITY:
        return False
    if capability not in record["capabilities"]:
        return False
    if contract_id is not None and contract_id not in [item["contract_id"] for item in record["contracts"]]:
        return False
    if target is not None and target not in record["platforms"]:
        return False
    if kind is not None and kind != record["kind"]:
        return False
    if max_effort is not None:
        effort = str((record.get("integration") or {}).get("estimated_effort", "high"))
        if EFFORT_ORDER.get(effort, 99) > EFFORT_ORDER[max_effort]:
            return False
    if require_stable_contract:
        relevant = record["contracts"]
        if contract_id is not None:
            relevant = [item for item in relevant if item["contract_id"] == contract_id]
        if not relevant or any(item.get("status") != "stable" for item in relevant):
            return False
    return True


def compare_records(left: dict, right: dict) -> int:
    lavailability = 1 if left["availability"] == "active" else 0
    ravailability = 1 if right["availability"] == "active" else 0
    if lavailability != ravailability:
        return -1 if lavailability > ravailability else 1

    lscore = float(left["ranking"]["score"])
    rscore = float(right["ranking"]["score"])
    if lscore != rscore:
        return -1 if lscore > rscore else 1

    lattempts = int(left["ranking"]["evidence"]["attempts"])
    rattempts = int(right["ranking"]["evidence"]["attempts"])
    if lattempts != rattempts:
        return -1 if lattempts > rattempts else 1

    semver = compare_semver(str(left["version"]), str(right["version"]))
    if semver != 0:
        return -semver

    left_id = str(left["id"])
    right_id = str(right["id"])
    if left_id == right_id:
        return 0
    return -1 if left_id < right_id else 1


def query(
    root: Path,
    *,
    capability: str,
    contract_id: str | None = None,
    target: str | None = None,
    kind: str | None = None,
    max_effort: str | None = None,
    include_deprecated: bool = False,
    include_adaptable: bool = False,
    require_stable_contract: bool = False,
) -> list[dict]:
    require(bool(capability.strip()), "capability is required")
    if max_effort is not None:
        require(max_effort in EFFORT_ORDER, f"invalid max effort: {max_effort}")

    registry = contract_map(root)
    records = []
    for entry in catalog(root)["assets"]:
        record = asset_record(root, entry, registry)
        if candidate_matches(
            record,
            capability=capability,
            contract_id=contract_id,
            target=target,
            kind=kind,
            max_effort=max_effort,
            include_deprecated=include_deprecated,
            include_adaptable=include_adaptable,
            require_stable_contract=require_stable_contract,
        ):
            records.append(record)
    records.sort(key=cmp_to_key(compare_records))
    return records


def resolve(root: Path, **filters: object) -> dict:
    candidates = query(root, **filters)
    return {
        "policy": {
            "id": POLICY_ID,
            "weights": dict(POLICY_WEIGHTS),
            "selection_scope": "rank eligible Library candidates only; Cantiere must separately compare reuse vs fresh implementation cost",
        },
        "filters": filters,
        "selected": None if not candidates else candidates[0],
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def all_asset_records(root: Path) -> list[dict]:
    registry = contract_map(root)
    records = [asset_record(root, entry, registry) for entry in catalog(root)["assets"]]
    records.sort(key=lambda value: (str(value["id"]), str(value["version"])))
    return records


def build_snapshot(root: Path) -> dict:
    catalog_data = catalog(root)
    contracts_data = contracts(root)
    needs_data = needs(root)
    lifecycle_path = root / "catalog" / "lifecycle.json"
    lifecycle_data = load_json(lifecycle_path) if lifecycle_path.exists() else {"schema_version": 1, "revision": 0, "updated_at": None, "events": []}

    payload = {
        "schema_version": 1,
        "library_id": catalog_data.get("library_id"),
        "catalog_version": catalog_data.get("catalog_version"),
        "source_state": {
            "catalog_updated_at": catalog_data.get("updated_at"),
            "contracts_updated_at": contracts_data.get("updated_at"),
            "needs_updated_at": needs_data.get("updated_at"),
            "lifecycle_revision": lifecycle_data.get("revision", 0),
            "lifecycle_updated_at": lifecycle_data.get("updated_at"),
        },
        "resolution_policy": {"id": POLICY_ID, "weights": dict(POLICY_WEIGHTS)},
        "contracts": sorted(contracts_data["contracts"], key=lambda value: str(value.get("contract_id"))),
        "needs": sorted(needs_data["items"], key=lambda value: str(value.get("capability_id"))),
        "assets": all_asset_records(root),
    }
    snapshot_hash = sha256_bytes(canonical_bytes(payload))
    return {**payload, "snapshot_sha256": snapshot_hash}


def export_snapshot(root: Path, output: Path) -> dict:
    snapshot = build_snapshot(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    return {"result": "exported", "output": str(output), "snapshot_sha256": snapshot["snapshot_sha256"], "asset_count": len(snapshot["assets"])}


def common_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--capability", required=True)
    parser.add_argument("--contract")
    parser.add_argument("--target")
    parser.add_argument("--kind")
    parser.add_argument("--max-effort", choices=sorted(EFFORT_ORDER, key=lambda value: EFFORT_ORDER[value]))
    parser.add_argument("--include-deprecated", action="store_true")
    parser.add_argument("--include-adaptable", action="store_true", help="include tested, evidenced candidates that require Cantiere adaptation")
    parser.add_argument("--require-stable-contract", action="store_true")


def filters_from_args(args: argparse.Namespace) -> dict:
    return {
        "capability": args.capability,
        "contract_id": args.contract,
        "target": args.target,
        "kind": args.kind,
        "max_effort": args.max_effort,
        "include_deprecated": args.include_deprecated,
        "include_adaptable": args.include_adaptable,
        "require_stable_contract": args.require_stable_contract,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Query and export AI Orchestrator Module Library state")
    result.add_argument("--root", type=Path, default=ROOT)
    sub = result.add_subparsers(dest="command", required=True)

    query_parser = sub.add_parser("query", help="return all eligible candidates in deterministic rank order")
    common_filters(query_parser)

    resolve_parser = sub.add_parser("resolve", help="return the best eligible candidate plus ranked alternatives")
    common_filters(resolve_parser)

    get_parser = sub.add_parser("get", help="inspect one exact catalogued asset version, regardless of availability")
    get_parser.add_argument("asset_id")
    get_parser.add_argument("version")

    export_parser = sub.add_parser("export-cache", help="write a deterministic offline Library snapshot")
    export_parser.add_argument("--output", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "query":
            output = {"candidates": query(root, **filters_from_args(args))}
        elif args.command == "resolve":
            output = resolve(root, **filters_from_args(args))
        elif args.command == "get":
            data = catalog(root)
            entry = next((item for item in data["assets"] if item.get("id") == args.asset_id and item.get("version") == args.version), None)
            require(entry is not None, f"asset not found: {args.asset_id}@{args.version}")
            output = asset_record(root, entry)
        else:
            output = export_snapshot(root, args.output.resolve())
        print(json.dumps(output, indent=2, ensure_ascii=False))
    except ResolverError as exc:
        print(f"LIBRARY RESOLVER FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
