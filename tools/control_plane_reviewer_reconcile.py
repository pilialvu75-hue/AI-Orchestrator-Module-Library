#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import control_plane_manager
import validate_control_plane

ROOT = Path(__file__).resolve().parents[1]
PENDING_REL = Path(".airlab/control-plane/inbox/pending")
PROCESSED_REL = Path(".airlab/control-plane/inbox/processed")
QUARANTINE_REL = Path(".airlab/control-plane/inbox/quarantine")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
OPERATION = "resolve_stale_block"
REVIEWER_ACTOR = "chatgpt:main-reviewer"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _lane_rel(root: Path, lane_id: str) -> Path:
    canonical = _load(root / ".airlab/control-plane/canonical-state.json")
    for rel in canonical.get("workstreams") or []:
        path = root / rel
        try:
            lane = _load(path)
        except Exception:
            continue
        if lane.get("id") == lane_id:
            return Path(rel)
    raise ValueError(f"unknown or unreadable lane: {lane_id}")


def _identity(request: dict[str, Any]) -> tuple[str, str, int, dict[str, Any]]:
    if request.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must match [A-Za-z0-9._-]{1,128}")
    if request.get("actor_id") != REVIEWER_ACTOR:
        raise ValueError("resolve_stale_block is restricted to chatgpt:main-reviewer")
    lane_id = request.get("lane_id")
    if not isinstance(lane_id, str) or not lane_id.strip():
        raise ValueError("lane_id is required")
    if request.get("operation") != OPERATION:
        raise ValueError(f"unsupported operation: {request.get('operation')}")
    expected = request.get("expected_state_version")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        raise ValueError("expected_state_version must be a non-negative integer")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    allowed = {
        "schema_version", "request_id", "submitted_at", "actor_id", "lane_id",
        "operation", "expected_state_version", "payload",
    }
    unknown = set(request) - allowed
    if unknown:
        raise ValueError("unsupported request fields: " + ", ".join(sorted(unknown)))
    return request_id, lane_id.strip(), expected, payload


def _resolve(root: Path, lane_id: str, payload: dict[str, Any], now: datetime) -> None:
    lane_path = root / _lane_rel(root, lane_id)
    lane = _load(lane_path)
    block = lane.get("block_reason") or {}
    if lane.get("status") != "BLOCKED" or block.get("code") != "CLAIM_LEASE_EXPIRED":
        raise ValueError(f"lane {lane_id} is not blocked by CLAIM_LEASE_EXPIRED")
    if lane.get("active_claim") is not None:
        raise ValueError("stale-block resolution requires active_claim=null after reconcile")

    work_item = str(payload.get("work_item") or "").strip()
    claim_id = str(payload.get("claim_id") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    next_action = str(payload.get("next_action") or "").strip()
    evidence_refs = payload.get("evidence_refs") or []
    if not work_item or not claim_id or not summary or not next_action:
        raise ValueError("resolve_stale_block requires work_item, claim_id, summary and next_action")
    if block.get("work_item") != work_item or block.get("claim_id") != claim_id:
        raise ValueError("stale-block identity does not match canonical block_reason")
    if not isinstance(evidence_refs, list) or not evidence_refs or any(
        not isinstance(item, str) or not item.strip() for item in evidence_refs
    ):
        raise ValueError("resolve_stale_block requires non-empty evidence_refs")

    event = {
        "type": "STALE_BLOCK_RESOLVED_BY_REVIEWER",
        "claim_id": claim_id,
        "work_item": work_item,
        "summary": summary,
        "evidence_refs": [item.strip() for item in evidence_refs],
        "at": _iso(now),
    }
    events = lane.setdefault("reconciliation_events", [])
    events.append(event)
    lane["reconciliation_events"] = events[-20:]
    history = lane.setdefault("stale_block_history", [])
    history.append({**block, "resolved_at": _iso(now), "resolution": event})
    lane["stale_block_history"] = history[-20:]
    lane.pop("block_reason", None)
    lane["status"] = "READY"
    lane["active_claim"] = None
    lane["next_action"] = next_action
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    _write(lane_path, lane)
    control_plane_manager.project(root=root, now=now)


def _receipt(request: dict[str, Any], request_id: str, status: str, now: datetime, errors: list[str], result_version: int | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "status": status,
        "processed_at": _iso(now),
        "source_file": f"{request_id}.json",
        "lane_id": request.get("lane_id"),
        "operation": request.get("operation"),
        "actor_id": request.get("actor_id"),
        "errors": errors,
        "result_state_version": result_version,
    }


def process_one(path: Path, *, root: Path = ROOT, now: datetime | None = None) -> str:
    now = now or _now()
    request = _load(path)
    request_id, lane_id, expected, payload = _identity(request)
    processed = root / PROCESSED_REL / f"{request_id}.json"
    quarantine = root / QUARANTINE_REL / f"{request_id}.json"
    if processed.exists() or quarantine.exists():
        path.unlink(missing_ok=True)
        return f"{request_id}: duplicate-noop"
    try:
        lane_rel = _lane_rel(root, lane_id)
        current = _load(root / lane_rel)
        if current.get("state_version") != expected:
            raise ValueError(f"state_version conflict: expected {expected}, current {current.get('state_version')}")
        baseline_errors = validate_control_plane.validate(root)
        with tempfile.TemporaryDirectory(prefix="control-plane-reviewer-reconcile-") as temp_name:
            temp_root = Path(temp_name)
            shutil.copytree(root / ".airlab", temp_root / ".airlab")
            _resolve(temp_root, lane_id, payload, now)
            candidate_errors = validate_control_plane.validate(temp_root)
            new_errors = sorted(set(candidate_errors) - set(baseline_errors))
            if new_errors:
                raise ValueError("candidate validation failed: " + " | ".join(new_errors))
            result = _load(temp_root / lane_rel)
            shutil.copy2(temp_root / lane_rel, root / lane_rel)
            shutil.copy2(
                temp_root / ".airlab/control-plane/canonical-state.json",
                root / ".airlab/control-plane/canonical-state.json",
            )
        _write(processed, _receipt(request, request_id, "APPLIED", now, [], int(result.get("state_version", 0))))
        path.unlink(missing_ok=True)
        return f"{request_id}: applied"
    except Exception as error:
        _write(quarantine, _receipt(request, request_id, "QUARANTINED", now, [str(error)], None))
        path.unlink(missing_ok=True)
        return f"{request_id}: quarantined: {error}"


def process(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    outcomes: list[str] = []
    for path in sorted((root / PENDING_REL).glob("*.json")):
        try:
            request = _load(path)
        except Exception:
            continue
        if request.get("operation") == OPERATION:
            outcomes.append(process_one(path, root=root, now=now))
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve reconciled stale-claim blocks under Main/Reviewer authority.")
    parser.add_argument("command", choices=["process"])
    parser.parse_args()
    for outcome in process():
        print(outcome)


if __name__ == "__main__":
    main()
