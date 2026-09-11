from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from functools import cmp_to_key
from pathlib import Path

from library_history import AssetRef, compare_semver, load_history, summarize_history

ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY = {"active", "deprecated", "revoked"}
TRANSITIONS = {
    ("active", "deprecated"),
    ("active", "revoked"),
    ("deprecated", "active"),
    ("deprecated", "revoked"),
}
SOURCES = {"library", "manual", "security", "cantiere"}


class LifecycleError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LifecycleError(message)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LifecycleError(f"invalid JSON at {path}: {exc}") from exc


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def bump_patch(version: str) -> str:
    core = version.split("-", 1)[0].split("+", 1)[0].split(".")
    require(len(core) == 3 and all(part.isdigit() for part in core), "catalog_version must be semantic")
    major, minor, patch = map(int, core)
    return f"{major}.{minor}.{patch + 1}"


def catalog(root: Path) -> tuple[Path, dict]:
    path = root / "catalog" / "index.json"
    data = load_json(path)
    require(isinstance(data.get("assets"), list), "catalog.assets must be an array")
    return path, data


def lifecycle(root: Path) -> tuple[Path, dict]:
    path = root / "catalog" / "lifecycle.json"
    data = load_json(path)
    require(data.get("schema_version") == 1, "unsupported lifecycle schema")
    require(isinstance(data.get("events"), list), "lifecycle.events must be an array")
    return path, data


def find_entry(data: dict, asset_id: str, version: str) -> dict:
    for item in data["assets"]:
        if item.get("id") == asset_id and item.get("version") == version:
            return item
    raise LifecycleError(f"asset is not registered: {asset_id}@{version}")


def availability(entry: dict) -> str:
    value = entry.get("availability", "active")
    require(value in AVAILABILITY, f"invalid catalog availability: {value}")
    return str(value)


def parse_replacement(value: str | None, catalog_data: dict) -> dict | None:
    if value is None:
        return None
    require("@" in value, "replacement must use <asset-id>@<version>")
    asset_id, version = value.rsplit("@", 1)
    require(bool(asset_id and version), "replacement must use <asset-id>@<version>")
    entry = find_entry(catalog_data, asset_id, version)
    require(availability(entry) != "revoked", "replacement cannot be revoked")
    return {"asset_id": asset_id, "version": version}


def event_matches(existing: dict, requested: dict) -> bool:
    return json.dumps(existing, sort_keys=True, separators=(",", ":")) == json.dumps(
        requested, sort_keys=True, separators=(",", ":")
    )


def apply_transition(
    root: Path,
    *,
    asset_id: str,
    version: str,
    target: str,
    reason: str,
    source: str,
    replacement_text: str | None = None,
    event_id: str | None = None,
    occurred_at: str | None = None,
) -> dict:
    require(target in AVAILABILITY, "invalid target availability")
    require(source in SOURCES, "invalid lifecycle source")
    require(len(reason.strip()) >= 3, "reason is required")

    catalog_path, catalog_data = catalog(root)
    ledger_path, ledger = lifecycle(root)
    entry = find_entry(catalog_data, asset_id, version)
    require(entry.get("status") == "certified", "lifecycle availability applies only to certified catalog assets")
    current = availability(entry)

    if current == target:
        return {
            "result": "already_in_state",
            "asset": f"{asset_id}@{version}",
            "availability": current,
        }

    require((current, target) in TRANSITIONS, f"forbidden lifecycle transition {current} -> {target}")
    replacement = parse_replacement(replacement_text, catalog_data)
    if replacement is not None:
        require(
            not (replacement["asset_id"] == asset_id and replacement["version"] == version),
            "replacement cannot point to the same asset version",
        )

    event = {
        "event_id": event_id or str(uuid.uuid4()),
        "asset_id": asset_id,
        "version": version,
        "from": current,
        "to": target,
        "occurred_at": occurred_at or utc_now(),
        "reason": reason.strip(),
        "source": source,
        "replacement": replacement,
    }

    for existing in ledger["events"]:
        if existing.get("event_id") != event["event_id"]:
            continue
        if event_matches(existing, event):
            require(availability(entry) == target, "existing lifecycle event does not match catalog state")
            return {"result": "already_applied", "event_id": event["event_id"], "availability": target}
        raise LifecycleError(f"event_id {event['event_id']} already exists with different content")

    old_catalog = catalog_path.read_bytes()
    old_ledger = ledger_path.read_bytes()
    try:
        entry["availability"] = target
        catalog_data["catalog_version"] = bump_patch(str(catalog_data.get("catalog_version", "0.0.0")))
        catalog_data["updated_at"] = utc_now()

        ledger["events"].append(event)
        ledger["revision"] = int(ledger.get("revision", 0)) + 1
        ledger["updated_at"] = utc_now()

        write_json(catalog_path, catalog_data)
        write_json(ledger_path, ledger)
    except Exception:
        catalog_path.write_bytes(old_catalog)
        ledger_path.write_bytes(old_ledger)
        raise

    return {
        "result": "transitioned",
        "asset": f"{asset_id}@{version}",
        "from": current,
        "to": target,
        "event_id": event["event_id"],
        "replacement": replacement,
    }


def rollback_plan(
    root: Path,
    *,
    asset_id: str,
    from_version: str,
    target: str | None = None,
    contract_id: str | None = None,
    include_deprecated: bool = False,
) -> dict:
    _, data = catalog(root)
    current = find_entry(data, asset_id, from_version)

    allowed = {"active"}
    if include_deprecated:
        allowed.add("deprecated")

    candidates: list[dict] = []
    for item in data["assets"]:
        if item.get("id") != asset_id:
            continue
        version = str(item.get("version", ""))
        if version == from_version or compare_semver(version, from_version) >= 0:
            continue
        if availability(item) not in allowed:
            continue
        if target and target not in (item.get("platforms") or []):
            continue
        if contract_id and contract_id not in (item.get("contracts") or []):
            continue
        candidates.append(item)

    candidates.sort(
        key=cmp_to_key(lambda left, right: compare_semver(str(left["version"]), str(right["version"]))),
        reverse=True,
    )

    enriched: list[dict] = []
    for item in candidates:
        ref = AssetRef(asset_id, str(item["version"]))
        history = load_history(root, ref)
        enriched.append(
            {
                "version": item["version"],
                "availability": availability(item),
                "platforms": item.get("platforms", []),
                "contracts": item.get("contracts", []),
                "observations": summarize_history(history),
            }
        )

    return {
        "asset_id": asset_id,
        "from_version": from_version,
        "from_availability": availability(current),
        "target": target,
        "contract_id": contract_id,
        "recommended": None if not enriched else enriched[0],
        "candidates": enriched,
        "automatic_switch_performed": False,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Manage certified asset availability and rollback planning")
    result.add_argument("--root", type=Path, default=ROOT)
    sub = result.add_subparsers(dest="command", required=True)

    for command, target in (("deprecate", "deprecated"), ("revoke", "revoked"), ("reinstate", "active")):
        action = sub.add_parser(command)
        action.set_defaults(target_state=target)
        action.add_argument("asset_id")
        action.add_argument("version")
        action.add_argument("--reason", required=True)
        action.add_argument("--source", choices=sorted(SOURCES), default="library")
        action.add_argument("--replacement")
        action.add_argument("--event-id")
        action.add_argument("--occurred-at")

    rollback = sub.add_parser("rollback-plan")
    rollback.add_argument("asset_id")
    rollback.add_argument("from_version")
    rollback.add_argument("--target")
    rollback.add_argument("--contract-id")
    rollback.add_argument("--include-deprecated", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "rollback-plan":
            output = rollback_plan(
                root,
                asset_id=args.asset_id,
                from_version=args.from_version,
                target=args.target,
                contract_id=args.contract_id,
                include_deprecated=args.include_deprecated,
            )
        else:
            output = apply_transition(
                root,
                asset_id=args.asset_id,
                version=args.version,
                target=args.target_state,
                reason=args.reason,
                source=args.source,
                replacement_text=args.replacement,
                event_id=args.event_id,
                occurred_at=args.occurred_at,
            )
        print(json.dumps(output, indent=2))
    except LifecycleError as exc:
        print(f"LIBRARY LIFECYCLE FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
