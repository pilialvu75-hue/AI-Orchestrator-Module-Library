#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_REL = Path(".airlab/control-plane/canonical-sync-receipts.json")
PENDING_REL = Path(".airlab/control-plane/inbox/pending")
PROCESSED_REL = Path(".airlab/control-plane/inbox/processed")
QUARANTINE_REL = Path(".airlab/control-plane/inbox/quarantine")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _roadmap_path(root: Path, ref: str) -> Path:
    raw = ref.split("#", 1)[0].strip()
    if raw == ".airlab/roadmap.yaml":
        rel = Path(raw)
    elif raw.startswith(".airlab/public-repositories/") and raw.endswith("/roadmap.yaml"):
        rel = Path(raw)
    else:
        raise ValueError(f"canonical sync ref is not an authoritative roadmap path: {ref}")
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe canonical sync ref: {ref}")
    path = root / rel
    if not path.is_file():
        raise ValueError(f"canonical sync roadmap ref does not exist: {ref}")
    return path


def _canonical(root: Path) -> dict[str, Any]:
    return _load(root / ".airlab/control-plane/canonical-state.json")


def _lane(root: Path, lane_id: str) -> dict[str, Any]:
    canonical = _canonical(root)
    for rel in canonical.get("workstreams") or []:
        try:
            lane = _load(root / rel)
        except Exception:
            continue
        if lane.get("id") == lane_id:
            return lane
    raise ValueError(f"unknown or unreadable lane: {lane_id}")


def _receipt_path(root: Path, folder: Path, request_id: str) -> Path:
    return root / folder / f"{request_id}.json"


def _request_id(request: dict[str, Any], fallback: str) -> str:
    value = request.get("request_id")
    if isinstance(value, str) and REQUEST_ID_RE.fullmatch(value):
        return value
    return fallback if REQUEST_ID_RE.fullmatch(fallback) else "invalid-canonical-sync-request"


def _quarantine(
    root: Path,
    path: Path,
    request: dict[str, Any],
    error: str,
    now: datetime,
) -> str:
    request_id = _request_id(request, path.stem)
    receipt = {
        "schema_version": 1,
        "request_id": request_id,
        "status": "QUARANTINED",
        "processed_at": _iso(now),
        "source_file": path.name,
        "lane_id": request.get("lane_id"),
        "operation": request.get("operation"),
        "actor_id": request.get("actor_id"),
        "errors": [error],
        "result_state_version": None,
    }
    _write(_receipt_path(root, QUARANTINE_REL, request_id), receipt)
    path.unlink(missing_ok=True)
    return f"{request_id}: quarantined: {error}"


def _key(lane_id: str, claim_id: str) -> str:
    return f"{lane_id}:{claim_id}"


def _records(registry: dict[str, Any]) -> list[dict[str, Any]]:
    records = registry.setdefault("records", [])
    if not isinstance(records, list):
        raise ValueError("canonical-sync receipt records must be a list")
    return records


def _record_by_key(registry: dict[str, Any], key: str) -> dict[str, Any] | None:
    for record in _records(registry):
        if isinstance(record, dict) and record.get("key") == key:
            return record
    return None


def _material_roadmap(lane: dict[str, Any]) -> tuple[bool, list[str], str | None]:
    packet = lane.get("review_packet") or {}
    roadmap = packet.get("roadmap_impact") or {}
    material = roadmap.get("material") is True
    refs = [str(item).strip() for item in (roadmap.get("refs") or []) if str(item).strip()]
    claim_id = packet.get("claim_id")
    return material, refs, str(claim_id) if claim_id else None


def _capture_review_baseline(
    root: Path,
    registry: dict[str, Any],
    request: dict[str, Any],
    request_id: str,
    now: datetime,
) -> None:
    lane_id = str(request.get("lane_id") or "").strip()
    if not lane_id:
        return
    lane = _lane(root, lane_id)
    if request.get("expected_state_version") != lane.get("state_version"):
        return
    material, refs, packet_claim_id = _material_roadmap(lane)
    claim = lane.get("active_claim") or {}
    claim_id = str(claim.get("claim_id") or "")
    if not material:
        return
    if not claim_id or not packet_claim_id or packet_claim_id != claim_id:
        raise ValueError("material review baseline requires review_packet claim_id to match active claim")
    if not refs:
        raise ValueError("material review baseline requires at least one roadmap ref")

    entries = []
    for ref in refs:
        path = _roadmap_path(root, ref)
        entries.append({
            "ref": ref,
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "before_sha256": _sha256(path),
        })

    key = _key(lane_id, claim_id)
    existing = _record_by_key(registry, key)
    record = {
        "key": key,
        "lane_id": lane_id,
        "claim_id": claim_id,
        "work_item": claim.get("work_item"),
        "status": "BASELINE_CAPTURED",
        "review_accept_request_id": request_id,
        "captured_at": _iso(now),
        "roadmap_refs": entries,
        "validated_completion": None,
        "completion": None,
    }
    if existing is None:
        _records(registry).append(record)
    else:
        if existing.get("status") == "RECONCILED":
            return
        if existing.get("roadmap_refs") != entries:
            raise ValueError("material review baseline changed for the same lane/claim")
        existing.update(record)


def _validate_completion(
    root: Path,
    registry: dict[str, Any],
    request: dict[str, Any],
    request_id: str,
    now: datetime,
) -> None:
    lane_id = str(request.get("lane_id") or "").strip()
    lane = _lane(root, lane_id)
    if request.get("expected_state_version") != lane.get("state_version"):
        return
    block = lane.get("block_reason") or {}
    if lane.get("status") != "BLOCKED" or block.get("code") != "CANONICAL_SYNC_REQUIRED":
        raise ValueError(f"lane {lane_id} is not blocked on canonical sync")
    claim_id = str(block.get("reviewed_claim_id") or "").strip()
    if not claim_id:
        raise ValueError("canonical sync block is missing reviewed_claim_id")
    expected_refs = [str(item).strip() for item in (block.get("roadmap_refs") or []) if str(item).strip()]
    if not expected_refs:
        raise ValueError("canonical sync block is missing roadmap refs")
    record = _record_by_key(registry, _key(lane_id, claim_id))
    if record is None:
        raise ValueError("canonical sync completion has no captured pre-sync digest record")

    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("canonical_sync_complete payload must be an object")
    supplied_refs = [str(item).strip() for item in (payload.get("refs") or []) if str(item).strip()]
    if set(supplied_refs) != set(expected_refs):
        raise ValueError("canonical sync refs must exactly match required roadmap refs")
    receipts = payload.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("canonical sync completion requires evidence-backed receipts")
    if len(receipts) != len(expected_refs):
        raise ValueError("canonical sync receipt count must match required roadmap refs")

    baseline = {entry["ref"]: entry for entry in record.get("roadmap_refs") or []}
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(receipts):
        if not isinstance(item, dict):
            raise ValueError(f"canonical sync receipts[{index}] must be an object")
        if set(item) != {"ref", "before_sha256", "after_sha256", "evidence_ref"}:
            raise ValueError(
                f"canonical sync receipts[{index}] must contain exactly ref, before_sha256, after_sha256, evidence_ref"
            )
        ref = str(item.get("ref") or "").strip()
        before = str(item.get("before_sha256") or "").lower().strip()
        after = str(item.get("after_sha256") or "").lower().strip()
        evidence_ref = str(item.get("evidence_ref") or "").strip()
        if ref not in expected_refs or ref in seen:
            raise ValueError(f"canonical sync receipt has unexpected/duplicate ref: {ref}")
        seen.add(ref)
        if not SHA256_RE.fullmatch(before) or not SHA256_RE.fullmatch(after):
            raise ValueError(f"canonical sync receipt digests must be lowercase sha256 for {ref}")
        if not evidence_ref:
            raise ValueError(f"canonical sync receipt evidence_ref is required for {ref}")
        expected_before = (baseline.get(ref) or {}).get("before_sha256")
        if before != expected_before:
            raise ValueError(f"canonical sync before digest does not match captured baseline for {ref}")
        current_after = _sha256(_roadmap_path(root, ref))
        if after != current_after:
            raise ValueError(f"canonical sync after digest does not match current roadmap content for {ref}")
        if before == after:
            raise ValueError(f"material canonical sync did not change roadmap content for {ref}")
        normalized.append({
            "ref": ref,
            "before_sha256": before,
            "after_sha256": after,
            "evidence_ref": evidence_ref,
        })

    record["validated_completion"] = {
        "request_id": request_id,
        "validated_at": _iso(now),
        "receipts": sorted(normalized, key=lambda item: item["ref"]),
    }


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append("canonical-sync receipts schema_version must be 1")
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        errors.append("canonical-sync receipts policy must be an object")
    elif policy.get("mode") != "evidence_backed_before_after_digest":
        errors.append("canonical-sync receipts policy mode is invalid")
    seen: set[str] = set()
    for index, record in enumerate(registry.get("records") or []):
        if not isinstance(record, dict):
            errors.append(f"canonical-sync receipt records[{index}] must be an object")
            continue
        key = record.get("key")
        if not isinstance(key, str) or not key or key in seen:
            errors.append(f"canonical-sync receipt records[{index}] has missing/duplicate key")
        else:
            seen.add(key)
        if record.get("status") not in {"BASELINE_CAPTURED", "RECONCILED"}:
            errors.append(f"canonical-sync receipt records[{index}] has invalid status")
        refs = record.get("roadmap_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"canonical-sync receipt records[{index}] requires roadmap_refs")
            continue
        for entry in refs:
            if not isinstance(entry, dict) or set(entry) != {"ref", "path", "before_sha256"}:
                errors.append(f"canonical-sync receipt records[{index}] has malformed roadmap ref baseline")
                continue
            if not SHA256_RE.fullmatch(str(entry.get("before_sha256") or "")):
                errors.append(f"canonical-sync receipt records[{index}] has invalid before_sha256")
        if record.get("status") == "RECONCILED":
            completion = record.get("completion")
            if not isinstance(completion, dict) or not completion.get("request_id"):
                errors.append(f"canonical-sync receipt records[{index}] RECONCILED requires completion")
    return errors


def prepare(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    registry_path = root / REGISTRY_REL
    registry = _load(registry_path)
    outcomes: list[str] = []
    policy = registry.setdefault("policy", {})
    if policy.get("enforcement_started_at") is None:
        policy["enforcement_started_at"] = _iso(now)

    for path in sorted((root / PENDING_REL).glob("*.json")):
        try:
            request = _load(path)
        except Exception:
            continue
        operation = request.get("operation")
        if operation not in {"review_accept", "canonical_sync_complete"}:
            continue
        request_id = _request_id(request, path.stem)
        try:
            if operation == "review_accept":
                _capture_review_baseline(root, registry, request, request_id, now)
            else:
                _validate_completion(root, registry, request, request_id, now)
        except Exception as error:
            outcomes.append(_quarantine(root, path, request, str(error), now))

    _write(registry_path, registry)
    return outcomes


def finalize(*, root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    registry_path = root / REGISTRY_REL
    registry = _load(registry_path)
    outcomes: list[str] = []
    kept: list[dict[str, Any]] = []
    for record in _records(registry):
        review_request = str(record.get("review_accept_request_id") or "")
        if review_request and _receipt_path(root, QUARANTINE_REL, review_request).exists():
            outcomes.append(f"{record.get('key')}: removed baseline after quarantined review_accept")
            continue

        validation = record.get("validated_completion")
        if isinstance(validation, dict):
            request_id = str(validation.get("request_id") or "")
            processed = _receipt_path(root, PROCESSED_REL, request_id)
            quarantined = _receipt_path(root, QUARANTINE_REL, request_id)
            if quarantined.exists():
                record["validated_completion"] = None
                outcomes.append(f"{record.get('key')}: completion validation cleared after quarantine")
            elif processed.exists():
                receipt = _load(processed)
                if receipt.get("status") != "APPLIED":
                    raise ValueError(f"processed canonical sync receipt is not APPLIED: {request_id}")
                lane = _lane(root, str(record.get("lane_id") or ""))
                if (lane.get("gates") or {}).get("G7_CANONICAL_SYNC") != "PASS":
                    raise ValueError(f"canonical sync request applied without G7 PASS: {request_id}")
                record["status"] = "RECONCILED"
                record["completion"] = {
                    "request_id": request_id,
                    "finalized_at": _iso(now),
                    "result_state_version": receipt.get("result_state_version"),
                    "receipts": validation.get("receipts") or [],
                }
                record["validated_completion"] = None
                outcomes.append(f"{record.get('key')}: reconciled")
        kept.append(record)
    registry["records"] = kept
    _write(registry_path, registry)
    return outcomes


def check(*, root: Path = ROOT) -> list[str]:
    registry = _load(root / REGISTRY_REL)
    errors = validate_registry(registry)
    start = (registry.get("policy") or {}).get("enforcement_started_at")
    records = {record.get("key"): record for record in registry.get("records") or [] if isinstance(record, dict)}
    if start:
        canonical = _canonical(root)
        for rel in canonical.get("workstreams") or []:
            try:
                lane = _load(root / rel)
            except Exception:
                continue
            material, _, claim_id = _material_roadmap(lane)
            if not material or not claim_id:
                continue
            reviewed_at = str((lane.get("reviewer") or {}).get("reviewed_at") or "")
            if not reviewed_at or reviewed_at < str(start):
                continue
            if (lane.get("gates") or {}).get("G7_CANONICAL_SYNC") != "PASS":
                continue
            key = _key(str(lane.get("id") or ""), claim_id)
            record = records.get(key)
            if not isinstance(record, dict) or record.get("status") != "RECONCILED":
                errors.append(
                    f"{lane.get('id')}: material G7_CANONICAL_SYNC=PASS requires finalized evidence-backed canonical sync receipt for claim {claim_id}"
                )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence-backed canonical roadmap sync receipt guard.")
    parser.add_argument("command", choices=["prepare", "finalize", "check"])
    args = parser.parse_args()
    if args.command == "prepare":
        for outcome in prepare():
            print(outcome)
        return
    if args.command == "finalize":
        for outcome in finalize():
            print(outcome)
        return
    errors = check()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print("Canonical sync receipts: PASS")


if __name__ == "__main__":
    main()
