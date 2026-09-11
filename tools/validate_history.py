from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
EVENT_TYPES = {"integration", "compatibility", "validation", "benchmark", "incident"}
SOURCES = {"cantiere", "library", "researcher", "manual", "ci"}
OUTCOMES = {"success", "failure", "compatible", "incompatible", "pass", "fail", "warning", "info"}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {exc}") from exc


def catalog_keys() -> set[tuple[str, str]]:
    path = ROOT / "catalog" / "index.json"
    data = load_json(path)
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise ValidationError("catalog/index.json: assets must be an array")
    result: set[tuple[str, str]] = set()
    for item in assets:
        if not isinstance(item, dict):
            raise ValidationError("catalog/index.json: asset entries must be objects")
        key = (str(item.get("id", "")), str(item.get("version", "")))
        result.add(key)
    return result


def validate_timestamp(value: object, label: str, path: Path) -> None:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{path.relative_to(ROOT)}: {label} must be a non-empty timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: {label} must be ISO-8601") from exc


def validate_event(event: object, seen: set[str], path: Path) -> None:
    if not isinstance(event, dict):
        raise ValidationError(f"{path.relative_to(ROOT)}: events must be objects")
    required = {"event_id", "type", "occurred_at", "source", "outcome"}
    missing = sorted(required - event.keys())
    if missing:
        raise ValidationError(f"{path.relative_to(ROOT)}: event missing {', '.join(missing)}")

    event_id = str(event["event_id"]).strip()
    if len(event_id) < 3:
        raise ValidationError(f"{path.relative_to(ROOT)}: event_id too short")
    if event_id in seen:
        raise ValidationError(f"{path.relative_to(ROOT)}: duplicate event_id {event_id}")
    seen.add(event_id)

    if event["type"] not in EVENT_TYPES:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid event type {event['type']}")
    if event["source"] not in SOURCES:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid event source {event['source']}")
    if event["outcome"] not in OUTCOMES:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid event outcome {event['outcome']}")
    validate_timestamp(event["occurred_at"], "event.occurred_at", path)

    score = event.get("score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
            raise ValidationError(f"{path.relative_to(ROOT)}: event.score must be between 0 and 1")


def validate_history_file(path: Path, registered: set[tuple[str, str]]) -> None:
    relative = path.relative_to(ROOT / "observations")
    if len(relative.parts) != 2:
        raise ValidationError(f"{path.relative_to(ROOT)}: expected observations/<asset-id>/<version>.json")
    asset_from_path = relative.parts[0]
    version_from_path = Path(relative.parts[1]).stem

    if ASSET_ID.fullmatch(asset_from_path) is None:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid asset id in path")
    if SEMVER.fullmatch(version_from_path) is None:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid version in filename")

    data = load_json(path)
    required = {"schema_version", "asset_id", "version", "revision", "updated_at", "events"}
    missing = sorted(required - data.keys())
    if missing:
        raise ValidationError(f"{path.relative_to(ROOT)}: missing {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise ValidationError(f"{path.relative_to(ROOT)}: unsupported schema_version")
    if data["asset_id"] != asset_from_path or data["version"] != version_from_path:
        raise ValidationError(f"{path.relative_to(ROOT)}: identity does not match path")

    key = (asset_from_path, version_from_path)
    if key not in registered:
        raise ValidationError(f"{path.relative_to(ROOT)}: observations refer to non-catalogued asset version")

    module_manifest = ROOT / "modules" / asset_from_path / version_from_path / "manifest.json"
    if not module_manifest.is_file():
        raise ValidationError(f"{path.relative_to(ROOT)}: observations require an existing module manifest")

    events = data["events"]
    if not isinstance(events, list):
        raise ValidationError(f"{path.relative_to(ROOT)}: events must be an array")
    revision = data["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValidationError(f"{path.relative_to(ROOT)}: revision must be a non-negative integer")
    if revision != len(events):
        raise ValidationError(f"{path.relative_to(ROOT)}: revision must equal append-only event count")
    if events:
        validate_timestamp(data["updated_at"], "updated_at", path)
    elif data["updated_at"] is not None:
        validate_timestamp(data["updated_at"], "updated_at", path)

    seen: set[str] = set()
    for event in events:
        validate_event(event, seen, path)


def main() -> int:
    try:
        registered = catalog_keys()
        root = ROOT / "observations"
        if root.exists():
            for path in sorted(root.glob("**/*.json")):
                validate_history_file(path, registered)
    except ValidationError as exc:
        print(f"LIBRARY HISTORY VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("LIBRARY HISTORY VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
