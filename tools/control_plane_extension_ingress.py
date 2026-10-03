#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PENDING_REL = Path(".airlab/control-plane/inbox/pending")
QUARANTINE_REL = Path(".airlab/control-plane/inbox/quarantine")
PROCESSED_REL = Path(".airlab/control-plane/inbox/processed")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
EXTENSION_OPERATIONS = {"enter_wait", "resume_wait", "resolve_stale_block"}
REVIEWER_ACTOR = "chatgpt:main-reviewer"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _validate_identity(request: dict[str, Any]) -> tuple[str, str, str, str, int]:
    if request.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must match [A-Za-z0-9._-]{1,128}")
    actor_id = request.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValueError("actor_id is required and must be non-empty")
    lane_id = request.get("lane_id")
    if not isinstance(lane_id, str) or not lane_id.strip():
        raise ValueError("lane_id is required and must be non-empty")
    operation = request.get("operation")
    if operation not in EXTENSION_OPERATIONS:
        raise ValueError(f"unsupported extension operation: {operation}")
    if operation == "resolve_stale_block" and actor_id != REVIEWER_ACTOR:
        raise ValueError("resolve_stale_block is restricted to chatgpt:main-reviewer")
    expected = request.get("expected_state_version")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        raise ValueError("expected_state_version must be a non-negative integer")
    if not isinstance(request.get("payload"), dict):
        raise ValueError("payload must be an object")
    allowed = {
        "schema_version", "request_id", "submitted_at", "actor_id", "lane_id",
        "operation", "expected_state_version", "payload",
    }
    unknown = set(request) - allowed
    if unknown:
        raise ValueError("unsupported request fields: " + ", ".join(sorted(unknown)))
    submitted_at = request.get("submitted_at")
    if submitted_at is not None and (not isinstance(submitted_at, str) or not submitted_at.strip()):
        raise ValueError("submitted_at must be a non-empty string when provided")
    return request_id, actor_id.strip(), lane_id.strip(), operation, expected


def _receipt(
    *,
    request: dict[str, Any] | None,
    request_id: str,
    source_file: str,
    now: datetime,
    error: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "status": "QUARANTINED",
        "processed_at": _iso(now),
        "source_file": source_file,
        "lane_id": request.get("lane_id") if request else None,
        "operation": request.get("operation") if request else None,
        "actor_id": request.get("actor_id") if request else None,
        "errors": [error],
        "result_state_version": None,
    }


def guard(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    outcomes: list[str] = []
    for path in sorted((root / PENDING_REL).glob("*.json")):
        request: dict[str, Any] | None = None
        fallback_id = path.stem if REQUEST_ID_RE.fullmatch(path.stem) else "invalid-extension-request"
        try:
            request = _load(path)
        except Exception:
            # The ordinary inbox owns generic malformed JSON quarantine. Extension routing
            # cannot be identified safely without a parsed operation, so leave it untouched.
            continue
        if request.get("operation") not in EXTENSION_OPERATIONS:
            continue
        request_id = request.get("request_id") if isinstance(request.get("request_id"), str) else fallback_id
        if not REQUEST_ID_RE.fullmatch(str(request_id)):
            request_id = fallback_id
        processed = root / PROCESSED_REL / f"{request_id}.json"
        quarantine = root / QUARANTINE_REL / f"{request_id}.json"
        if processed.exists() or quarantine.exists():
            path.unlink(missing_ok=True)
            outcomes.append(f"{request_id}: duplicate-noop")
            continue
        try:
            _validate_identity(request)
        except Exception as error:
            _write(
                quarantine,
                _receipt(
                    request=request,
                    request_id=str(request_id),
                    source_file=path.name,
                    now=now,
                    error=str(error),
                ),
            )
            path.unlink(missing_ok=True)
            outcomes.append(f"{request_id}: quarantined: {error}")
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail-closed ingress guard for control-plane extension operations.")
    parser.add_argument("command", choices=["guard"])
    parser.parse_args()
    for outcome in guard():
        print(outcome)


if __name__ == "__main__":
    main()
