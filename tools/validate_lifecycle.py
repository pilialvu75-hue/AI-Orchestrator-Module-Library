from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY = {"active", "deprecated", "revoked"}
TRANSITIONS = {
    ("active", "deprecated"),
    ("active", "revoked"),
    ("deprecated", "active"),
    ("deprecated", "revoked"),
}
SOURCES = {"library", "manual", "security", "cantiere"}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {exc}") from exc


def validate_timestamp(value: object, label: str, path: Path) -> None:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{path.relative_to(ROOT)}: {label} must be a non-empty timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: {label} must be ISO-8601") from exc


def main() -> int:
    try:
        catalog_path = ROOT / "catalog" / "index.json"
        lifecycle_path = ROOT / "catalog" / "lifecycle.json"
        catalog = load_json(catalog_path)
        ledger = load_json(lifecycle_path)

        assets = catalog.get("assets")
        if not isinstance(assets, list):
            raise ValidationError("catalog/index.json: assets must be an array")

        entries: dict[tuple[str, str], dict] = {}
        for item in assets:
            if not isinstance(item, dict):
                raise ValidationError("catalog/index.json: asset entry must be an object")
            key = (str(item.get("id", "")), str(item.get("version", "")))
            if not all(key):
                raise ValidationError("catalog/index.json: lifecycle validation requires id + version")
            if key in entries:
                raise ValidationError(f"catalog/index.json: duplicate asset {key[0]}@{key[1]}")
            value = item.get("availability", "active")
            if value not in AVAILABILITY:
                raise ValidationError(f"catalog/index.json: invalid availability {value} for {key[0]}@{key[1]}")
            entries[key] = item

        if ledger.get("schema_version") != 1:
            raise ValidationError("catalog/lifecycle.json: unsupported schema_version")
        events = ledger.get("events")
        if not isinstance(events, list):
            raise ValidationError("catalog/lifecycle.json: events must be an array")
        revision = ledger.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision != len(events):
            raise ValidationError("catalog/lifecycle.json: revision must equal event count")
        if events:
            validate_timestamp(ledger.get("updated_at"), "updated_at", lifecycle_path)

        state: dict[tuple[str, str], str] = {key: "active" for key in entries}
        seen_ids: set[str] = set()
        for event in events:
            if not isinstance(event, dict):
                raise ValidationError("catalog/lifecycle.json: events must be objects")
            required = {"event_id", "asset_id", "version", "from", "to", "occurred_at", "reason", "source"}
            missing = sorted(required - event.keys())
            if missing:
                raise ValidationError(f"catalog/lifecycle.json: event missing {', '.join(missing)}")
            event_id = str(event["event_id"]).strip()
            if len(event_id) < 3:
                raise ValidationError("catalog/lifecycle.json: event_id too short")
            if event_id in seen_ids:
                raise ValidationError(f"catalog/lifecycle.json: duplicate event_id {event_id}")
            seen_ids.add(event_id)

            key = (str(event["asset_id"]), str(event["version"]))
            if key not in entries:
                raise ValidationError(f"catalog/lifecycle.json: event references missing asset {key[0]}@{key[1]}")
            before = str(event["from"])
            after = str(event["to"])
            if (before, after) not in TRANSITIONS:
                raise ValidationError(f"catalog/lifecycle.json: forbidden transition {before}->{after}")
            if state[key] != before:
                raise ValidationError(
                    f"catalog/lifecycle.json: transition chain mismatch for {key[0]}@{key[1]}: expected {state[key]}, got {before}"
                )
            if event["source"] not in SOURCES:
                raise ValidationError(f"catalog/lifecycle.json: invalid source {event['source']}")
            if not isinstance(event["reason"], str) or len(event["reason"].strip()) < 3:
                raise ValidationError("catalog/lifecycle.json: transition reason is required")
            validate_timestamp(event["occurred_at"], "event.occurred_at", lifecycle_path)

            replacement = event.get("replacement")
            if replacement is not None:
                if not isinstance(replacement, dict):
                    raise ValidationError("catalog/lifecycle.json: replacement must be object or null")
                replacement_key = (str(replacement.get("asset_id", "")), str(replacement.get("version", "")))
                if replacement_key not in entries:
                    raise ValidationError(
                        f"catalog/lifecycle.json: replacement missing from catalog: {replacement_key[0]}@{replacement_key[1]}"
                    )
                if replacement_key == key:
                    raise ValidationError("catalog/lifecycle.json: replacement cannot point to itself")

            state[key] = after

        for key, item in entries.items():
            declared = str(item.get("availability", "active"))
            if state[key] != declared:
                raise ValidationError(
                    f"catalog/index.json: availability {declared} does not match lifecycle ledger state {state[key]} for {key[0]}@{key[1]}"
                )

    except ValidationError as exc:
        print(f"LIBRARY LIFECYCLE VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("LIBRARY LIFECYCLE VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
