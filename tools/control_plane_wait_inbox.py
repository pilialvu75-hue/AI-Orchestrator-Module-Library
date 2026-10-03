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

import control_plane_inbox
import control_plane_manager
import validate_control_plane

ROOT = Path(__file__).resolve().parents[1]
PENDING_REL = Path(".airlab/control-plane/inbox/pending")
PROCESSED_REL = Path(".airlab/control-plane/inbox/processed")
QUARANTINE_REL = Path(".airlab/control-plane/inbox/quarantine")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
WAIT_OPERATIONS = {"enter_wait", "resume_wait"}
WAIT_TYPES = {"WAITING_OWNER", "WAITING_EXTERNAL"}


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


def _request_identity(request: dict[str, Any]) -> tuple[str, str, str, int, dict[str, Any]]:
    if request.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must match [A-Za-z0-9._-]{1,128}")
    actor_id = request.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValueError("actor_id is required")
    lane_id = request.get("lane_id")
    if not isinstance(lane_id, str) or not lane_id.strip():
        raise ValueError("lane_id is required")
    operation = request.get("operation")
    if operation not in WAIT_OPERATIONS:
        raise ValueError(f"unsupported wait operation: {operation}")
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
    return request_id, lane_id.strip(), operation, expected, payload


def _authorize(root: Path, request: dict[str, Any], lane_id: str, operation: str) -> None:
    actor_id = str(request.get("actor_id") or "")
    if not actor_id.startswith("automation:"):
        return
    # CP-HARDEN-04 predates explicit wait operations. Until the canonical registry schema
    # is versioned again, entering a wait inherits release authority and resuming a wait
    # inherits claim authority. Ownership/target checks still come from the canonical registry.
    mapped_operation = "release" if operation == "enter_wait" else "claim"
    control_plane_inbox._authorize_automation_actor(root, actor_id, lane_id, mapped_operation)


def _validate_waits(root: Path) -> list[str]:
    errors: list[str] = []
    canonical = _load(root / ".airlab/control-plane/canonical-state.json")
    reserved_work: dict[str, str] = {}
    reserved_locks: dict[str, str] = {}
    for rel in canonical.get("workstreams") or []:
        path = root / rel
        try:
            lane = _load(path)
        except Exception:
            continue
        lane_id = str(lane.get("id") or rel)
        wait = lane.get("wait_state")
        if wait is None:
            continue
        if not isinstance(wait, dict):
            errors.append(f"{lane_id}: wait_state must be an object")
            continue
        if lane.get("status") != "BLOCKED":
            errors.append(f"{lane_id}: wait_state requires BLOCKED status")
        if lane.get("active_claim") is not None:
            errors.append(f"{lane_id}: wait_state requires active_claim=null")
        wait_type = wait.get("type")
        if wait_type not in WAIT_TYPES:
            errors.append(f"{lane_id}: invalid wait_state type {wait_type}")
        work_item = wait.get("work_item")
        if not isinstance(work_item, str) or not work_item.strip():
            errors.append(f"{lane_id}: wait_state missing work_item")
        elif work_item in reserved_work:
            errors.append(f"duplicate wait work_item {work_item}: {reserved_work[work_item]} and {lane_id}")
        else:
            reserved_work[work_item] = lane_id
        locks = wait.get("resource_locks") or []
        if not isinstance(locks, list) or any(not isinstance(item, str) or not item for item in locks):
            errors.append(f"{lane_id}: wait_state resource_locks must be a list of strings")
            locks = []
        for key in locks:
            owner = reserved_locks.get(key)
            if owner:
                errors.append(f"duplicate wait resource lock {key}: {owner} and {lane_id}")
            else:
                reserved_locks[key] = lane_id
        block = lane.get("block_reason") or {}
        if block.get("code") != wait_type:
            errors.append(f"{lane_id}: wait block_reason code must match wait_state type")
        if not wait.get("entered_at") or not wait.get("wait_id") or not wait.get("resume_condition"):
            errors.append(f"{lane_id}: wait_state requires wait_id, entered_at and resume_condition")
    return errors


def _enter_wait(root: Path, lane_id: str, payload: dict[str, Any], now: datetime) -> None:
    lane_path = root / _lane_rel(root, lane_id)
    lane = _load(lane_path)
    claim = lane.get("active_claim")
    if not isinstance(claim, dict):
        raise ValueError(f"lane {lane_id} has no active claim")
    control_plane_manager._assert_claim_live(claim, now)
    if lane.get("status") not in {"CLAIMED", "IMPLEMENTING", "EVIDENCE_READY"}:
        raise ValueError(f"lane {lane_id} cannot enter wait from {lane.get('status')}")
    wait_type = payload.get("wait_type")
    if wait_type not in WAIT_TYPES:
        raise ValueError("wait_type must be WAITING_OWNER or WAITING_EXTERNAL")
    resume_condition = str(payload.get("resume_condition") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    next_action = str(payload.get("next_action") or "").strip()
    if not resume_condition or not summary or not next_action:
        raise ValueError("enter_wait requires resume_condition, summary and next_action")
    evidence_refs = payload.get("evidence_refs") or []
    if not isinstance(evidence_refs, list) or any(not isinstance(item, str) or not item.strip() for item in evidence_refs):
        raise ValueError("enter_wait evidence_refs must be a list of non-empty strings")
    wait_id = f"{lane_id}:{claim.get('claim_id')}:{wait_type}"
    wait_state = {
        "schema_version": 1,
        "wait_id": wait_id,
        "type": wait_type,
        "work_item": claim.get("work_item"),
        "prior_claim_id": claim.get("claim_id"),
        "repository": claim.get("repository"),
        "branch": claim.get("branch"),
        "scope": claim.get("scope"),
        "resource_locks": list(claim.get("resource_locks") or []),
        "entered_at": _iso(now),
        "resume_condition": resume_condition,
        "summary": summary,
        "evidence_refs": [item.strip() for item in evidence_refs],
        "resume_next_action": next_action,
    }
    lane["wait_state"] = wait_state
    lane["active_claim"] = None
    lane["status"] = "BLOCKED"
    lane["block_reason"] = {
        "code": wait_type,
        "wait_id": wait_id,
        "work_item": wait_state["work_item"],
        "resource_locks": wait_state["resource_locks"],
        "resume_condition": resume_condition,
        "detected_at": _iso(now),
        "review_required": False,
    }
    lane["next_action"] = next_action
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    events = lane.setdefault("reconciliation_events", [])
    events.append({
        "type": "WAIT_ENTERED",
        "wait_id": wait_id,
        "wait_type": wait_type,
        "prior_claim_id": claim.get("claim_id"),
        "work_item": claim.get("work_item"),
        "resource_locks": wait_state["resource_locks"],
        "at": _iso(now),
    })
    lane["reconciliation_events"] = events[-20:]
    _write(lane_path, lane)
    control_plane_manager.project(root=root, now=now)


def _resume_wait(root: Path, lane_id: str, payload: dict[str, Any], now: datetime) -> None:
    lane_path = root / _lane_rel(root, lane_id)
    lane = _load(lane_path)
    wait = lane.get("wait_state")
    if lane.get("status") != "BLOCKED" or not isinstance(wait, dict):
        raise ValueError(f"lane {lane_id} is not in a machine-readable wait")
    signal_id = str(payload.get("signal_id") or "").strip()
    evidence_refs = payload.get("evidence_refs") or []
    if not signal_id:
        raise ValueError("resume_wait requires signal_id")
    if not isinstance(evidence_refs, list) or not evidence_refs or any(
        not isinstance(item, str) or not item.strip() for item in evidence_refs
    ):
        raise ValueError("resume_wait requires non-empty evidence_refs")
    next_action = str(payload.get("next_action") or wait.get("resume_next_action") or "").strip()
    if not next_action:
        raise ValueError("resume_wait requires next_action or a stored resume_next_action")
    history = lane.setdefault("wait_history", [])
    history.append({
        **wait,
        "resumed_at": _iso(now),
        "signal_id": signal_id,
        "resume_evidence_refs": [item.strip() for item in evidence_refs],
    })
    lane["wait_history"] = history[-20:]
    events = lane.setdefault("reconciliation_events", [])
    events.append({
        "type": "WAIT_RESUMED",
        "wait_id": wait.get("wait_id"),
        "work_item": wait.get("work_item"),
        "signal_id": signal_id,
        "evidence_refs": [item.strip() for item in evidence_refs],
        "at": _iso(now),
    })
    lane["reconciliation_events"] = events[-20:]
    lane.pop("wait_state", None)
    lane.pop("block_reason", None)
    lane["active_claim"] = None
    lane["status"] = "READY"
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


def process_wait_request(path: Path, *, root: Path = ROOT, now: datetime | None = None) -> str:
    now = now or _now()
    request = _load(path)
    request_id, lane_id, operation, expected, payload = _request_identity(request)
    processed = root / PROCESSED_REL / f"{request_id}.json"
    quarantine = root / QUARANTINE_REL / f"{request_id}.json"
    if processed.exists() or quarantine.exists():
        path.unlink(missing_ok=True)
        return f"{request_id}: duplicate-noop"
    try:
        _authorize(root, request, lane_id, operation)
        lane_rel = _lane_rel(root, lane_id)
        current = _load(root / lane_rel)
        if current.get("state_version") != expected:
            raise ValueError(f"state_version conflict: expected {expected}, current {current.get('state_version')}")
        baseline_errors = validate_control_plane.validate(root) + _validate_waits(root)
        with tempfile.TemporaryDirectory(prefix="control-plane-wait-") as temp_name:
            temp_root = Path(temp_name)
            shutil.copytree(root / ".airlab", temp_root / ".airlab")
            if operation == "enter_wait":
                _enter_wait(temp_root, lane_id, payload, now)
            else:
                _resume_wait(temp_root, lane_id, payload, now)
            candidate_errors = validate_control_plane.validate(temp_root) + _validate_waits(temp_root)
            new_errors = sorted(set(candidate_errors) - set(baseline_errors))
            if new_errors:
                raise ValueError("candidate validation failed: " + " | ".join(new_errors))
            result = _load(temp_root / lane_rel)
            shutil.copy2(temp_root / lane_rel, root / lane_rel)
            shutil.copy2(temp_root / ".airlab/control-plane/canonical-state.json", root / ".airlab/control-plane/canonical-state.json")
        _write(processed, _receipt(request, request_id, "APPLIED", now, [], int(result.get("state_version", 0))))
        path.unlink(missing_ok=True)
        return f"{request_id}: applied"
    except Exception as error:
        _write(quarantine, _receipt(request, request_id, "QUARANTINED", now, [str(error)], None))
        path.unlink(missing_ok=True)
        return f"{request_id}: quarantined: {error}"


def _wait_reservations(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    canonical = _load(root / ".airlab/control-plane/canonical-state.json")
    work: dict[str, str] = {}
    locks: dict[str, str] = {}
    for rel in canonical.get("workstreams") or []:
        try:
            lane = _load(root / rel)
        except Exception:
            continue
        wait = lane.get("wait_state")
        if not isinstance(wait, dict):
            continue
        lane_id = str(lane.get("id") or rel)
        item = wait.get("work_item")
        if isinstance(item, str) and item:
            work[item] = lane_id
        for key in wait.get("resource_locks") or []:
            if isinstance(key, str) and key:
                locks[key] = lane_id
    return work, locks


def preflight_claim_requests(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    work_reservations, lock_reservations = _wait_reservations(root)
    outcomes: list[str] = []
    pending = root / PENDING_REL
    for path in sorted(pending.glob("*.json")):
        try:
            request = _load(path)
        except Exception:
            continue
        if request.get("operation") != "claim":
            continue
        request_id = str(request.get("request_id") or path.stem)
        payload = request.get("payload") or {}
        work_item = payload.get("work_item")
        conflict = None
        if work_item in work_reservations:
            conflict = f"wait reservation conflict: work_item {work_item} is reserved by {work_reservations[work_item]}"
        else:
            try:
                requested_locks = control_plane_manager._normalize_resource_locks(
                    payload.get("resource_locks"),
                    repository=str(payload.get("repository") or ""),
                    branch=payload.get("branch"),
                )
            except ValueError:
                continue
            overlap = sorted(set(requested_locks).intersection(lock_reservations))
            if overlap:
                owners = sorted({lock_reservations[key] for key in overlap})
                conflict = f"wait reservation conflict with {owners}: {', '.join(overlap)}"
        if conflict:
            quarantine = root / QUARANTINE_REL / f"{request_id}.json"
            _write(quarantine, _receipt(request, request_id, "QUARANTINED", now, [conflict], None))
            path.unlink(missing_ok=True)
            outcomes.append(f"{request_id}: quarantined: {conflict}")
    return outcomes


def process(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    outcomes: list[str] = []
    pending = root / PENDING_REL
    for path in sorted(pending.glob("*.json")):
        try:
            request = _load(path)
        except Exception:
            continue
        if request.get("operation") in WAIT_OPERATIONS:
            outcomes.append(process_wait_request(path, root=root, now=now))
    outcomes.extend(preflight_claim_requests(root=root, now=now))
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="Process machine-readable control-plane wait lifecycle requests.")
    parser.add_argument("command", choices=["process", "validate"])
    args = parser.parse_args()
    if args.command == "process":
        for outcome in process():
            print(outcome)
    else:
        errors = _validate_waits(ROOT)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            raise SystemExit(1)
        print("Control-plane wait validation: PASS")


if __name__ == "__main__":
    main()
