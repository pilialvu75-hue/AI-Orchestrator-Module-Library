from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cmp_to_key
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
SEMVER = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)
EVENT_TYPES = {"integration", "compatibility", "validation", "benchmark", "incident"}
SOURCES = {"cantiere", "library", "researcher", "manual", "ci"}
OUTCOMES = {
    "success",
    "failure",
    "compatible",
    "incompatible",
    "pass",
    "fail",
    "warning",
    "info",
}


class HistoryError(Exception):
    pass


@dataclass(frozen=True)
class AssetRef:
    asset_id: str
    version: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HistoryError(message)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HistoryError(f"invalid JSON at {path}: {exc}") from exc


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_ref(ref: AssetRef) -> None:
    require(ASSET_ID.fullmatch(ref.asset_id) is not None, "invalid asset id")
    require(SEMVER.fullmatch(ref.version) is not None, "invalid semantic version")


def parse_semver(value: str) -> tuple[int, int, int, str | None]:
    match = SEMVER.fullmatch(value)
    if match is None:
        raise HistoryError(f"invalid semantic version: {value}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4)


def compare_prerelease(left: str | None, right: str | None) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1

    left_parts = left.split(".")
    right_parts = right.split(".")
    for lpart, rpart in zip(left_parts, right_parts):
        if lpart == rpart:
            continue
        lnum = lpart.isdigit()
        rnum = rpart.isdigit()
        if lnum and rnum:
            return -1 if int(lpart) < int(rpart) else 1
        if lnum != rnum:
            return -1 if lnum else 1
        return -1 if lpart < rpart else 1
    if len(left_parts) == len(right_parts):
        return 0
    return -1 if len(left_parts) < len(right_parts) else 1


def compare_semver(left: str, right: str) -> int:
    lmajor, lminor, lpatch, lpre = parse_semver(left)
    rmajor, rminor, rpatch, rpre = parse_semver(right)
    lcore = (lmajor, lminor, lpatch)
    rcore = (rmajor, rminor, rpatch)
    if lcore != rcore:
        return -1 if lcore < rcore else 1
    return compare_prerelease(lpre, rpre)


def history_path(root: Path, ref: AssetRef) -> Path:
    return root / "observations" / ref.asset_id / f"{ref.version}.json"


def catalog_entries(root: Path) -> list[dict]:
    catalog = load_json(root / "catalog" / "index.json")
    assets = catalog.get("assets")
    require(isinstance(assets, list), "catalog assets must be an array")
    return assets


def catalog_entry(root: Path, ref: AssetRef) -> dict:
    validate_ref(ref)
    for item in catalog_entries(root):
        if item.get("id") == ref.asset_id and item.get("version") == ref.version:
            return item
    raise HistoryError(f"asset is not registered in catalog: {ref.asset_id}@{ref.version}")


def new_history(ref: AssetRef) -> dict:
    return {
        "schema_version": 1,
        "asset_id": ref.asset_id,
        "version": ref.version,
        "revision": 0,
        "updated_at": None,
        "events": [],
    }


def load_history(root: Path, ref: AssetRef) -> dict:
    path = history_path(root, ref)
    if not path.exists():
        return new_history(ref)
    value = load_json(path)
    require(value.get("asset_id") == ref.asset_id, "history asset_id does not match path")
    require(value.get("version") == ref.version, "history version does not match path")
    require(isinstance(value.get("events"), list), "history events must be an array")
    return value


def canonical_event(event: dict) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def validate_event(event: dict) -> None:
    require(isinstance(event.get("event_id"), str) and len(event["event_id"].strip()) >= 3, "event_id is required")
    require(event.get("type") in EVENT_TYPES, "invalid event type")
    require(event.get("source") in SOURCES, "invalid event source")
    require(event.get("outcome") in OUTCOMES, "invalid event outcome")
    occurred_at = event.get("occurred_at")
    require(isinstance(occurred_at, str) and occurred_at, "occurred_at is required")
    try:
        datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoryError("occurred_at must be ISO-8601") from exc
    score = event.get("score")
    if score is not None:
        require(isinstance(score, (int, float)) and not isinstance(score, bool), "score must be numeric")
        require(0 <= float(score) <= 1, "score must be between 0 and 1")


def record_event(root: Path, ref: AssetRef, event: dict) -> dict:
    catalog_entry(root, ref)
    validate_event(event)
    history = load_history(root, ref)

    for existing in history["events"]:
        if existing.get("event_id") != event["event_id"]:
            continue
        if canonical_event(existing) == canonical_event(event):
            return {"result": "already_recorded", "event_id": event["event_id"], "revision": history["revision"]}
        raise HistoryError(f"event_id {event['event_id']} already exists with different content")

    history["events"].append(event)
    history["revision"] = int(history.get("revision", 0)) + 1
    history["updated_at"] = utc_now()
    write_json(history_path(root, ref), history)
    return {"result": "recorded", "event_id": event["event_id"], "revision": history["revision"]}


def compatibility_key(event: dict) -> str:
    return f"{event.get('target') or '*'}::{event.get('contract_id') or '*'}"


def summarize_history(history: dict) -> dict:
    successes = 0
    failures = 0
    compatibility: dict[str, dict] = {}
    latest_validation: dict | None = None
    benchmark_count = 0
    incident_count = 0

    for event in history.get("events", []):
        event_type = event.get("type")
        outcome = event.get("outcome")
        if event_type == "integration":
            if outcome == "success":
                successes += 1
            elif outcome == "failure":
                failures += 1
        elif event_type == "compatibility":
            compatibility[compatibility_key(event)] = {
                "outcome": outcome,
                "occurred_at": event.get("occurred_at"),
                "target": event.get("target"),
                "contract_id": event.get("contract_id"),
                "notes": event.get("notes"),
            }
        elif event_type == "validation":
            latest_validation = {
                "outcome": outcome,
                "score": event.get("score"),
                "occurred_at": event.get("occurred_at"),
                "target": event.get("target"),
            }
        elif event_type == "benchmark":
            benchmark_count += 1
        elif event_type == "incident":
            incident_count += 1

    attempts = successes + failures
    return {
        "revision": int(history.get("revision", 0)),
        "reuse_count": attempts,
        "successful_integrations": successes,
        "failed_integrations": failures,
        "success_rate": None if attempts == 0 else successes / attempts,
        "compatibility": compatibility,
        "latest_validation": latest_validation,
        "benchmark_count": benchmark_count,
        "incident_count": incident_count,
        "last_observed_at": history.get("updated_at"),
    }


def summary(root: Path, ref: AssetRef) -> dict:
    entry = catalog_entry(root, ref)
    history = load_history(root, ref)
    return {
        "asset_id": ref.asset_id,
        "version": ref.version,
        "catalog_status": entry.get("status"),
        "platforms": entry.get("platforms", []),
        "contracts": entry.get("contracts", []),
        "observations": summarize_history(history),
    }


def compare_versions(root: Path, asset_id: str) -> dict:
    require(ASSET_ID.fullmatch(asset_id) is not None, "invalid asset id")
    entries = [item for item in catalog_entries(root) if item.get("id") == asset_id]
    require(entries, f"asset has no catalog versions: {asset_id}")
    entries.sort(key=cmp_to_key(lambda left, right: compare_semver(str(left["version"]), str(right["version"]))))

    versions: list[dict] = []
    for entry in entries:
        ref = AssetRef(asset_id, str(entry["version"]))
        versions.append(summary(root, ref))
    return {"asset_id": asset_id, "versions": versions, "latest_version": versions[-1]["version"]}


def parse_metadata(value: str | None) -> dict:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HistoryError("--metadata must be valid JSON") from exc
    require(isinstance(parsed, dict), "--metadata must be a JSON object")
    return parsed


def build_event(args: argparse.Namespace) -> dict:
    event = {
        "event_id": args.event_id or str(uuid.uuid4()),
        "type": args.type,
        "occurred_at": args.occurred_at or utc_now(),
        "source": args.source,
        "outcome": args.outcome,
        "target": args.target,
        "contract_id": args.contract_id,
        "project_id": args.project_id,
        "score": args.score,
        "notes": args.notes,
        "metadata": parse_metadata(args.metadata),
    }
    validate_event(event)
    return event


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Record and inspect immutable-module operational history")
    result.add_argument("--root", type=Path, default=ROOT)
    sub = result.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="append an idempotent observation to one certified/catalogued asset version")
    record.add_argument("asset_id")
    record.add_argument("version")
    record.add_argument("--event-id")
    record.add_argument("--type", required=True, choices=sorted(EVENT_TYPES))
    record.add_argument("--source", required=True, choices=sorted(SOURCES))
    record.add_argument("--outcome", required=True, choices=sorted(OUTCOMES))
    record.add_argument("--occurred-at")
    record.add_argument("--target")
    record.add_argument("--contract-id")
    record.add_argument("--project-id")
    record.add_argument("--score", type=float)
    record.add_argument("--notes")
    record.add_argument("--metadata")

    inspect = sub.add_parser("summary", help="summarize history for one asset version")
    inspect.add_argument("asset_id")
    inspect.add_argument("version")

    compare = sub.add_parser("compare", help="compare all catalogued versions in one asset lineage")
    compare.add_argument("asset_id")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "record":
            ref = AssetRef(args.asset_id, args.version)
            print(json.dumps(record_event(root, ref, build_event(args)), indent=2))
        elif args.command == "summary":
            print(json.dumps(summary(root, AssetRef(args.asset_id, args.version)), indent=2))
        else:
            print(json.dumps(compare_versions(root, args.asset_id), indent=2))
    except HistoryError as exc:
        print(f"LIBRARY HISTORY FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
