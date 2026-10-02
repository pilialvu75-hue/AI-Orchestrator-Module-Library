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

import chat_checkpoint
import control_plane_manager
import validate_control_plane

ROOT = Path(__file__).resolve().parents[1]
PENDING_REL = Path(".airlab/control-plane/inbox/pending")
PROCESSED_REL = Path(".airlab/control-plane/inbox/processed")
QUARANTINE_REL = Path(".airlab/control-plane/inbox/quarantine")
AUTOMATION_REGISTRY_REL = Path(".airlab/control-plane/automation-registry.json")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
OPERATIONS = {
    "claim",
    "heartbeat",
    "checkpoint",
    "release",
    "submit_review",
    "review_accept",
    "review_rework",
    "canonical_sync_complete",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")
    return data


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _canonical(root: Path) -> dict[str, Any]:
    return _load(root / ".airlab/control-plane/canonical-state.json")


def _automation_registry(root: Path) -> dict[str, Any]:
    path = root / AUTOMATION_REGISTRY_REL
    if not path.exists():
        raise ValueError("canonical automation registry is missing")
    registry = _load(path)
    if registry.get("schema_version") != 1:
        raise ValueError("canonical automation registry schema_version must be 1")
    return registry


def _lane_rel(root: Path, lane_id: str) -> Path:
    canonical = _canonical(root)
    for rel in canonical.get("workstreams") or []:
        path = root / rel
        try:
            lane = _load(path)
        except Exception:
            continue
        if lane.get("id") == lane_id:
            return Path(rel)
    raise ValueError(f"unknown or unreadable lane: {lane_id}")


def _authorize_automation_actor(
    root: Path,
    actor_id: str,
    lane_id: str,
    operation: str,
) -> dict[str, Any] | None:
    registry = _automation_registry(root)
    policy = registry.get("policy") or {}
    prefix = str(policy.get("automation_actor_prefix") or "automation:")
    if not actor_id.startswith(prefix):
        return None

    matches = [
        entry for entry in (registry.get("automations") or [])
        if entry.get("actor_id") == actor_id
    ]
    if len(matches) != 1:
        if not matches:
            raise ValueError(f"automation actor is not registered: {actor_id}")
        raise ValueError(f"automation actor is registered more than once: {actor_id}")

    entry = matches[0]
    if entry.get("enabled") is not True:
        raise ValueError(f"automation actor is disabled by canonical registry: {actor_id}")
    if "control_plane_mutation" not in (entry.get("write_capabilities") or []):
        raise ValueError(f"automation actor lacks control_plane_mutation capability: {actor_id}")
    if operation not in (entry.get("allowed_operations") or []):
        raise ValueError(f"automation actor operation is not allowed: {actor_id} -> {operation}")

    owner_lane = entry.get("owner_lane")
    if not isinstance(owner_lane, str) or not owner_lane:
        raise ValueError(f"automation actor has no canonical owner lane: {actor_id}")

    target_policy = entry.get("target_lane_policy")
    if target_policy == "owner_lane_only":
        if lane_id != owner_lane:
            raise ValueError(
                f"automation actor may mutate only owner lane {owner_lane}; target={lane_id}"
            )
    elif target_policy == "worker_lanes_only":
        lane_rel = _lane_rel(root, lane_id)
        lane = _load(root / lane_rel)
        if lane.get("role") == "reviewer" or lane_id == owner_lane:
            raise ValueError(
                f"automation actor may target worker lanes only; target={lane_id}"
            )
    elif target_policy == "explicit":
        allowed = entry.get("allowed_target_lanes") or []
        if lane_id not in allowed:
            raise ValueError(
                f"automation actor target lane is not allowed: {actor_id} -> {lane_id}"
            )
    elif target_policy == "all_canonical_lanes":
        _lane_rel(root, lane_id)
    else:
        raise ValueError(
            f"automation actor target_lane_policy forbids mutation: {actor_id} -> {target_policy}"
        )
    return entry


def _request_identity(request: dict[str, Any], fallback: str) -> tuple[str, str, str, int, dict[str, Any]]:
    if request.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must match [A-Za-z0-9._-]{1,128}")
    lane_id = request.get("lane_id")
    if not isinstance(lane_id, str) or not lane_id.strip():
        raise ValueError("lane_id must be a non-empty string")
    operation = request.get("operation")
    if operation not in OPERATIONS:
        raise ValueError(f"unsupported operation: {operation}")
    expected = request.get("expected_state_version")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        raise ValueError("expected_state_version must be a non-negative integer")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    allowed = {
        "schema_version", "request_id", "submitted_at", "actor_id",
        "lane_id", "operation", "expected_state_version", "payload",
    }
    unknown = set(request) - allowed
    if unknown:
        raise ValueError("unsupported request fields: " + ", ".join(sorted(unknown)))
    submitted_at = request.get("submitted_at")
    if submitted_at is not None and (not isinstance(submitted_at, str) or not submitted_at.strip()):
        raise ValueError("submitted_at must be a non-empty string when provided")
    actor_id = request.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValueError("actor_id is required and must be a non-empty string")
    return request_id, lane_id.strip(), operation, expected, payload


def _apply(
    root: Path,
    lane_id: str,
    operation: str,
    payload: dict[str, Any],
    now: datetime,
) -> None:
    if operation == "claim":
        control_plane_manager.claim(
            lane_id,
            payload.get("work_item"),
            payload.get("repository"),
            payload.get("scope"),
            branch=payload.get("branch"),
            resource_locks=payload.get("resource_locks"),
            lease_hours=payload.get("lease_hours"),
            root=root,
            now=now,
        )
    elif operation == "heartbeat":
        control_plane_manager.heartbeat(
            lane_id,
            lease_hours=payload.get("lease_hours"),
            root=root,
            now=now,
        )
    elif operation == "checkpoint":
        decisions = payload.get("decisions") or []
        evidence_refs = payload.get("evidence_refs") or []
        if not isinstance(decisions, list) or not all(isinstance(item, str) for item in decisions):
            raise ValueError("checkpoint decisions must be a list of strings")
        if not isinstance(evidence_refs, list) or not all(isinstance(item, str) for item in evidence_refs):
            raise ValueError("checkpoint evidence_refs must be a list of strings")
        chat_checkpoint.checkpoint(
            lane_id,
            str(payload.get("summary") or ""),
            str(payload.get("next_action") or ""),
            decisions=decisions,
            evidence_refs=evidence_refs,
            root=root,
            now=now,
        )
    elif operation == "release":
        control_plane_manager.release(
            lane_id,
            reason=str(payload.get("reason") or ""),
            root=root,
            now=now,
        )
    elif operation == "submit_review":
        packet = payload.get("packet")
        if not isinstance(packet, dict):
            raise ValueError("submit_review payload.packet must be an object")
        packet_path = root / ".airlab/control-plane/.transaction-review-packet.json"
        _write(packet_path, packet)
        try:
            control_plane_manager.submit_review(
                lane_id,
                packet_path,
                root=root,
                now=now,
            )
        finally:
            packet_path.unlink(missing_ok=True)
    elif operation == "review_accept":
        evidence_refs = payload.get("evidence_refs") or []
        if not isinstance(evidence_refs, list) or not all(isinstance(item, str) for item in evidence_refs):
            raise ValueError("review_accept evidence_refs must be a list of strings")
        control_plane_manager.review_accept(
            lane_id,
            summary=str(payload.get("summary") or ""),
            next_action=str(payload.get("next_action") or ""),
            evidence_refs=evidence_refs,
            root=root,
            now=now,
        )
    elif operation == "review_rework":
        control_plane_manager.review_rework(
            lane_id,
            reason=str(payload.get("reason") or ""),
            next_action=str(payload.get("next_action") or ""),
            root=root,
            now=now,
        )
    elif operation == "canonical_sync_complete":
        refs = payload.get("refs") or []
        if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
            raise ValueError("canonical_sync_complete refs must be a list of strings")
        control_plane_manager.canonical_sync_complete(
            lane_id,
            refs=refs,
            root=root,
            now=now,
        )
    else:
        raise ValueError(f"unsupported operation: {operation}")


def _copy_airlab(source_root: Path, target_root: Path) -> None:
    shutil.copytree(source_root / ".airlab", target_root / ".airlab")


def _target_errors(errors: list[str], lane_id: str) -> list[str]:
    prefix = f"{lane_id}:"
    return [item for item in errors if item.startswith(prefix)]


def _receipt(
    *,
    request: dict[str, Any] | None,
    request_id: str,
    status: str,
    processed_at: datetime,
    source_file: str,
    errors: list[str] | None = None,
    result_state_version: int | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "status": status,
        "processed_at": _iso(processed_at),
        "source_file": source_file,
        "lane_id": request.get("lane_id") if request else None,
        "operation": request.get("operation") if request else None,
        "actor_id": request.get("actor_id") if request else None,
        "errors": errors or [],
        "result_state_version": result_state_version,
    }


def process_one(path: Path, *, root: Path = ROOT, now: datetime | None = None) -> str:
    now = now or _now()
    request: dict[str, Any] | None = None
    fallback_id = path.stem if REQUEST_ID_RE.fullmatch(path.stem) else "invalid-request"
    request_id = fallback_id
    try:
        request = _load(path)
        request_id, lane_id, operation, expected_version, payload = _request_identity(request, fallback_id)
        processed_path = root / PROCESSED_REL / f"{request_id}.json"
        quarantine_path = root / QUARANTINE_REL / f"{request_id}.json"
        if processed_path.exists() or quarantine_path.exists():
            path.unlink(missing_ok=True)
            return f"{request_id}: duplicate-noop"

        _authorize_automation_actor(
            root,
            str(request.get("actor_id")),
            lane_id,
            operation,
        )

        lane_rel = _lane_rel(root, lane_id)
        current_lane = _load(root / lane_rel)
        current_version = current_lane.get("state_version")
        if current_version != expected_version:
            raise ValueError(
                f"state_version conflict: expected {expected_version}, current {current_version}"
            )

        try:
            baseline_errors = validate_control_plane.validate(root)
        except Exception as error:
            baseline_errors = [f"validator baseline failure: {type(error).__name__}: {error}"]

        with tempfile.TemporaryDirectory(prefix="control-plane-transaction-") as tmp:
            temp_root = Path(tmp)
            _copy_airlab(root, temp_root)
            _apply(temp_root, lane_id, operation, payload, now)
            candidate_errors = validate_control_plane.validate(temp_root)
            target_errors = _target_errors(candidate_errors, lane_id)
            new_errors = sorted(set(candidate_errors) - set(baseline_errors))
            if target_errors or new_errors:
                errors = sorted(set(target_errors + new_errors))
                raise ValueError("candidate validation failed: " + " | ".join(errors))

            result_lane = _load(temp_root / lane_rel)
            result_version = result_lane.get("state_version")
            shutil.copy2(temp_root / lane_rel, root / lane_rel)
            shutil.copy2(
                temp_root / ".airlab/control-plane/canonical-state.json",
                root / ".airlab/control-plane/canonical-state.json",
            )

        _write(
            processed_path,
            _receipt(
                request=request,
                request_id=request_id,
                status="APPLIED",
                processed_at=now,
                source_file=path.name,
                result_state_version=result_version,
            ),
        )
        path.unlink(missing_ok=True)
        return f"{request_id}: applied"
    except Exception as error:
        quarantine_path = root / QUARANTINE_REL / f"{request_id}.json"
        if not quarantine_path.exists():
            _write(
                quarantine_path,
                _receipt(
                    request=request,
                    request_id=request_id,
                    status="QUARANTINED",
                    processed_at=now,
                    source_file=path.name,
                    errors=[f"{type(error).__name__}: {error}"],
                ),
            )
        path.unlink(missing_ok=True)
        return f"{request_id}: quarantined: {error}"


def process_all(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    pending = root / PENDING_REL
    pending.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    for path in sorted(pending.glob("*.json")):
        results.append(process_one(path, root=root, now=now))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply control-plane mutation requests transactionally.")
    parser.add_argument("command", choices=["process"])
    args = parser.parse_args()
    if args.command == "process":
        results = process_all()
        print("\n".join(results) if results else "no pending requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
