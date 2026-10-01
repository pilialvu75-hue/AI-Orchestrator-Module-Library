#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REL = Path(".airlab/control-plane/canonical-state.json")
REGISTRY_REL = Path(".airlab/control-plane/chat-registry.json")
DEFAULT_LEASE_HOURS = 12
MAX_LEASE_HOURS = 24


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _date(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def _canonical(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / CANONICAL_REL
    return path, _load(path)


def _lane_paths(root: Path, canonical: dict[str, Any]) -> list[Path]:
    return [root / Path(rel) for rel in canonical.get("workstreams", [])]


def _lanes(root: Path, canonical: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, _load(path)) for path in _lane_paths(root, canonical)]


def _lane_by_id(root: Path, canonical: dict[str, Any], lane_id: str) -> tuple[Path, dict[str, Any]]:
    for path, lane in _lanes(root, canonical):
        if lane.get("id") == lane_id:
            return path, lane
    raise ValueError(f"unknown lane: {lane_id}")


def _allowed_repositories_for_lane(root: Path, lane_id: str) -> set[str]:
    registry = _load(root / REGISTRY_REL)
    for entry in registry.get("lanes") or []:
        if entry.get("id") != lane_id:
            continue
        allowed = {str(entry.get("primary_repository") or "").strip()}
        allowed.update(str(item).strip() for item in (entry.get("secondary_repositories") or []))
        return {item for item in allowed if item}
    raise ValueError(f"lane {lane_id} is missing from chat registry")


def _lease_policy(canonical: dict[str, Any]) -> tuple[int, int]:
    policy = canonical.get("claim_policy") or {}
    default_hours = int(policy.get("default_lease_hours", DEFAULT_LEASE_HOURS))
    max_hours = int(policy.get("max_lease_hours", MAX_LEASE_HOURS))
    return default_hours, max_hours


def _assert_claim_live(claim_data: dict[str, Any], now: datetime) -> None:
    lease_until = claim_data.get("lease_until")
    if not lease_until:
        raise ValueError("active claim missing lease_until")
    if _parse_iso(str(lease_until)) <= now:
        raise ValueError(
            f"claim lease expired at {lease_until}; reconcile/reviewer action is required before more worker progress"
        )


def _checkpoint_watch_policy(canonical: dict[str, Any]) -> int:
    policy = canonical.get("continuous_checkpoint_policy") or {}
    watchdog = policy.get("watchdog") or {}
    minutes = int(watchdog.get("warning_after_minutes", 120))
    if minutes <= 0:
        raise ValueError("continuous checkpoint watchdog warning_after_minutes must be positive")
    return minutes


def _projection_payload(
    lanes: list[tuple[Path, dict[str, Any]]],
    *,
    now: datetime,
    checkpoint_warning_minutes: int,
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    active_claims: list[dict[str, Any]] = []
    review_required: list[str] = []
    blocked: list[dict[str, Any]] = []
    checkpoint_watch: list[dict[str, Any]] = []
    platform_profiles: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for _, lane in sorted(lanes, key=lambda item: str(item[1].get("id", ""))):
        lane_id = str(lane.get("id"))
        state = str(lane.get("status"))
        counts[state] += 1

        claim = lane.get("active_claim")
        claim_summary = None
        if claim:
            claim_summary = {
                "claim_id": claim.get("claim_id"),
                "work_item": claim.get("work_item"),
                "repository": claim.get("repository"),
                "lease_until": claim.get("lease_until"),
            }
            active_claims.append({"lane": lane_id, **claim_summary})

            checkpoint = lane.get("last_checkpoint") or {}
            same_claim = checkpoint.get("claim_id") == claim.get("claim_id")
            base_at_raw = checkpoint.get("at") if same_claim else claim.get("started_at")
            if base_at_raw:
                base_at = _parse_iso(str(base_at_raw))
                due_at = base_at + timedelta(minutes=checkpoint_warning_minutes)
                if now >= due_at:
                    checkpoint_watch.append({
                        "lane": lane_id,
                        "claim_id": claim.get("claim_id"),
                        "work_item": claim.get("work_item"),
                        "status": state,
                        "reason": "CHECKPOINT_STALE" if same_claim else "NO_CHECKPOINT_YET",
                        "last_checkpoint_at": checkpoint.get("at") if same_claim else None,
                        "due_since": _iso(due_at),
                        "warning_after_minutes": checkpoint_warning_minutes,
                    })

        if state == "REVIEW_REQUIRED":
            review_required.append(lane_id)
        if state == "BLOCKED":
            blocked.append({
                "lane": lane_id,
                "reason": lane.get("block_reason"),
            })

        profile = lane.get("inference_profile")
        if lane_id.startswith("platform-") and profile:
            platform_profiles.append({
                "lane": lane_id,
                "status": profile.get("status"),
                "backend": profile.get("backend"),
                "accelerator": profile.get("accelerator"),
                "selected_models_by_role": profile.get("selected_models_by_role") or {},
            })

        summaries.append({
            "id": lane_id,
            "status": state,
            "activation": lane.get("activation"),
            "state_version": lane.get("state_version"),
            "updated_at": lane.get("updated_at"),
            "active_claim": claim_summary,
            "reviewer_state": (lane.get("reviewer") or {}).get("state"),
            "inference_profile_status": (profile or {}).get("status") if profile else None,
            "historical_backlog_count": len(lane.get("historical_backlog") or []),
            "next_action": lane.get("next_action"),
        })

    return {
        "counts": dict(sorted(counts.items())),
        "active_claims": sorted(active_claims, key=lambda item: (item["lane"], item.get("work_item") or "")),
        "review_required": sorted(review_required),
        "blocked": sorted(blocked, key=lambda item: item["lane"]),
        "checkpoint_watch": sorted(checkpoint_watch, key=lambda item: item["lane"]),
        "platform_inference_profiles": sorted(platform_profiles, key=lambda item: item["lane"]),
        "lanes": summaries,
    }


def project(root: Path = ROOT, now: datetime | None = None) -> bool:
    now = now or _now()
    canonical_path, canonical = _canonical(root)
    checkpoint_warning_minutes = _checkpoint_watch_policy(canonical)
    payload = _projection_payload(
        _lanes(root, canonical),
        now=now,
        checkpoint_warning_minutes=checkpoint_warning_minutes,
    )
    digest_source = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()

    previous = canonical.get("projection") or {}
    if previous.get("source_digest") == digest:
        return False

    canonical["projection"] = {
        "source_digest": digest,
        "projected_at": _iso(now),
        **payload,
    }
    canonical["state_revision"] = int(canonical.get("state_revision", 0)) + 1
    canonical["updated_at"] = _date(now)
    _write(canonical_path, canonical)
    return True


def claim(
    lane_id: str,
    work_item: str,
    repository: str,
    scope: str,
    *,
    branch: str | None = None,
    lease_hours: int | None = None,
    root: Path = ROOT,
    now: datetime | None = None,
) -> str:
    now = now or _now()
    if not isinstance(work_item, str) or not work_item.strip():
        raise ValueError("work_item must be a non-empty string")
    if not isinstance(repository, str) or not repository.strip():
        raise ValueError("repository must be a non-empty string")
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("scope must be a non-empty string")
    allowed_repositories = _allowed_repositories_for_lane(root, lane_id)
    if repository not in allowed_repositories:
        raise ValueError(
            f"repository {repository} is outside lane {lane_id} scope; allowed={sorted(allowed_repositories)}"
        )
    canonical_path, canonical = _canonical(root)
    default_hours, max_hours = _lease_policy(canonical)
    hours = default_hours if lease_hours is None else int(lease_hours)
    if hours <= 0 or hours > max_hours:
        raise ValueError(f"lease_hours must be between 1 and {max_hours}")

    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    if lane.get("active_claim"):
        raise ValueError(f"lane {lane_id} already has an active claim")
    if lane.get("status") != "READY":
        raise ValueError(f"lane {lane_id} must be READY to claim work; current={lane.get('status')}")

    for _, other in _lanes(root, canonical):
        other_claim = other.get("active_claim")
        if other_claim and other_claim.get("work_item") == work_item:
            raise ValueError(f"work_item already claimed by {other.get('id')}: {work_item}")

    seed = f"{lane_id}|{work_item}|{_iso(now)}"
    claim_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    lease_until = now + timedelta(hours=hours)

    previous_packet = lane.pop("review_packet", None)
    if previous_packet:
        history = lane.setdefault("review_packet_history", [])
        history.append(previous_packet)
        lane["review_packet_history"] = history[-20:]
    lane["evidence"] = []
    if lane.get("role") != "reviewer":
        lane["reviewer"] = {
            "required": True,
            "state": "PENDING",
            "reviewed_by": None,
            "reviewed_at": None,
        }

    gates = lane.setdefault("gates", {})
    gates.update({
        "G0_CLAIM": "PASS",
        "G1_IMPLEMENTATION": "PENDING",
        "G2_STATIC": "PENDING",
        "G3_CI": "PENDING",
        "G4_INTEGRATION": "PENDING",
        "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE",
        "G7_CANONICAL_SYNC": "PENDING",
    })
    if lane.get("role") == "reviewer":
        gates["G6_REVIEWER"] = "SELF_AUTHORITY_FOR_CROSS_LANE_REVIEW_ONLY"
    else:
        gates["G6_REVIEWER"] = "PENDING"

    lane["active_claim"] = {
        "claim_id": claim_id,
        "owner_lane": lane_id,
        "work_item": work_item,
        "repository": repository,
        "scope": scope,
        "branch": branch,
        "started_at": _iso(now),
        "heartbeat_at": _iso(now),
        "lease_until": _iso(lease_until),
        "lease_hours": hours,
    }
    lane["status"] = "CLAIMED"
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    lane.pop("block_reason", None)
    _write(lane_path, lane)

    project(root=root, now=now)
    return claim_id


def heartbeat(
    lane_id: str,
    *,
    lease_hours: int | None = None,
    root: Path = ROOT,
    now: datetime | None = None,
) -> str:
    now = now or _now()
    _, canonical = _canonical(root)
    default_hours, max_hours = _lease_policy(canonical)
    hours = default_hours if lease_hours is None else int(lease_hours)
    if hours <= 0 or hours > max_hours:
        raise ValueError(f"lease_hours must be between 1 and {max_hours}")

    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    claim_data = lane.get("active_claim")
    if not claim_data:
        raise ValueError(f"lane {lane_id} has no active claim")
    _assert_claim_live(claim_data, now)

    claim_data["heartbeat_at"] = _iso(now)
    claim_data["lease_until"] = _iso(now + timedelta(hours=hours))
    claim_data["lease_hours"] = hours
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    _write(lane_path, lane)
    project(root=root, now=now)
    return str(claim_data["lease_until"])


def release(
    lane_id: str,
    *,
    reason: str,
    root: Path = ROOT,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    _, canonical = _canonical(root)
    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    claim_data = lane.get("active_claim")
    if not claim_data:
        raise ValueError(f"lane {lane_id} has no active claim")
    try:
        _assert_claim_live(claim_data, now)
    except ValueError as error:
        raise ValueError(f"release cannot bypass an expired claim: {error}") from error

    events = lane.setdefault("reconciliation_events", [])
    events.append({
        "type": "CLAIM_RELEASED",
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "reason": reason,
        "at": _iso(now),
    })
    lane["reconciliation_events"] = events[-20:]
    lane["active_claim"] = None
    lane["status"] = "READY"
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    lane["evidence"] = []
    lane.pop("review_packet", None)
    gates = lane.setdefault("gates", {})
    gates.update({
        "G0_CLAIM": "PENDING",
        "G1_IMPLEMENTATION": "PENDING",
        "G2_STATIC": "PENDING",
        "G3_CI": "PENDING",
        "G4_INTEGRATION": "PENDING",
        "G5_TARGET_RUNTIME": "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE",
        "G7_CANONICAL_SYNC": "PENDING",
    })
    if lane.get("role") == "reviewer":
        gates["G6_REVIEWER"] = "SELF_AUTHORITY_FOR_CROSS_LANE_REVIEW_ONLY"
    else:
        gates["G6_REVIEWER"] = "PENDING"
        lane["reviewer"] = {
            "required": True,
            "state": "PENDING",
            "reviewed_by": None,
            "reviewed_at": None,
        }
    _write(lane_path, lane)
    project(root=root, now=now)


def _validate_review_packet(lane_id: str, claim_data: dict[str, Any], packet: dict[str, Any]) -> None:
    required = (
        "schema_version", "submitted_at", "lane_id", "claim_id", "work_item",
        "repository", "summary", "changes", "evidence", "known_risks",
        "reviewer_checks", "roadmap_impact",
    )
    for field in required:
        if field not in packet:
            raise ValueError(f"review packet missing {field}")
    if packet.get("schema_version") != 1:
        raise ValueError("review packet schema_version must be 1")
    if packet.get("lane_id") != lane_id:
        raise ValueError("review packet lane_id mismatch")
    if packet.get("claim_id") != claim_data.get("claim_id"):
        raise ValueError("review packet claim_id mismatch")
    if packet.get("work_item") != claim_data.get("work_item"):
        raise ValueError("review packet work_item mismatch")
    if packet.get("repository") != claim_data.get("repository"):
        raise ValueError("review packet repository mismatch")
    for field in ("submitted_at", "lane_id", "claim_id", "work_item", "repository", "summary"):
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            raise ValueError(f"review packet {field} must be a non-empty string")

    branch = packet.get("branch")
    if branch is not None and not isinstance(branch, str):
        raise ValueError("review packet branch must be a string or null")
    pull_request = packet.get("pull_request")
    if pull_request is not None and (not isinstance(pull_request, int) or isinstance(pull_request, bool) or pull_request < 1):
        raise ValueError("review packet pull_request must be a positive integer or null")

    changes = packet.get("changes")
    if not isinstance(changes, list) or not changes or any(
        not isinstance(item, str) or not item.strip() for item in changes
    ):
        raise ValueError("review packet changes must be a non-empty list of non-empty strings")

    allowed_evidence_types = {
        "ci", "test", "diagnostics", "runtime", "physical_device",
        "commit", "pull_request", "analysis", "other",
    }
    allowed_results = {"PASS", "FAIL", "INFO", "PENDING"}
    evidence = packet.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("review packet evidence must be a non-empty list")
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise ValueError(f"review packet evidence[{index}] must be an object")
        if set(item) - {"type", "ref", "result", "note"}:
            raise ValueError(f"review packet evidence[{index}] contains unsupported fields")
        if item.get("type") not in allowed_evidence_types:
            raise ValueError(f"review packet evidence[{index}].type is invalid")
        if not isinstance(item.get("ref"), str) or not item["ref"].strip():
            raise ValueError(f"review packet evidence[{index}].ref must be a non-empty string")
        if item.get("result") not in allowed_results:
            raise ValueError(f"review packet evidence[{index}].result is invalid")
        if "note" in item and item["note"] is not None and not isinstance(item["note"], str):
            raise ValueError(f"review packet evidence[{index}].note must be a string or null")

    risks = packet.get("known_risks")
    if not isinstance(risks, list) or any(not isinstance(item, str) for item in risks):
        raise ValueError("review packet known_risks must be a list of strings")

    checks = packet.get("reviewer_checks")
    if not isinstance(checks, list) or not checks or any(
        not isinstance(item, str) or not item.strip() for item in checks
    ):
        raise ValueError("review packet reviewer_checks must be a non-empty list of non-empty strings")

    roadmap = packet.get("roadmap_impact")
    if not isinstance(roadmap, dict) or set(roadmap) != {"material", "refs"}:
        raise ValueError("review packet roadmap_impact must contain exactly material and refs")
    if not isinstance(roadmap.get("material"), bool):
        raise ValueError("review packet roadmap_impact.material must be boolean")
    refs = roadmap.get("refs")
    if not isinstance(refs, list) or any(not isinstance(item, str) or not item.strip() for item in refs):
        raise ValueError("review packet roadmap_impact.refs must be a list of non-empty strings")


def review_inbox(root: Path = ROOT) -> list[dict[str, Any]]:
    _, canonical = _canonical(root)
    items: list[dict[str, Any]] = []
    for _, lane in _lanes(root, canonical):
        if lane.get("role") == "reviewer" or lane.get("status") != "REVIEW_REQUIRED":
            continue
        claim_data = lane.get("active_claim") or {}
        packet = lane.get("review_packet") or {}
        packet_valid = True
        packet_error = None
        try:
            _validate_review_packet(str(lane.get("id")), claim_data, packet)
        except ValueError as error:
            packet_valid = False
            packet_error = str(error)
        items.append({
            "lane_id": lane.get("id"),
            "state_version": lane.get("state_version"),
            "claim_id": claim_data.get("claim_id"),
            "work_item": claim_data.get("work_item"),
            "repository": claim_data.get("repository"),
            "packet_valid": packet_valid,
            "packet_error": packet_error,
            "next_action": lane.get("next_action"),
        })
    return sorted(items, key=lambda item: str(item.get("lane_id") or ""))


def _review_gate_passed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("PASS")


def review_accept(
    lane_id: str,
    *,
    summary: str,
    next_action: str,
    evidence_refs: list[str] | None = None,
    root: Path = ROOT,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    _, canonical = _canonical(root)
    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    if lane.get("role") == "reviewer":
        raise ValueError("reviewer lane cannot review itself")
    if lane.get("status") != "REVIEW_REQUIRED":
        raise ValueError(f"lane {lane_id} must be REVIEW_REQUIRED; current={lane.get('status')}")
    claim_data = lane.get("active_claim")
    if not claim_data:
        raise ValueError(f"lane {lane_id} REVIEW_REQUIRED has no active claim")
    packet = lane.get("review_packet") or {}
    _validate_review_packet(lane_id, claim_data, packet)
    gates = lane.setdefault("gates", {})
    missing_gates = [
        gate for gate in ("G0_CLAIM", "G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION")
        if not _review_gate_passed(gates.get(gate))
    ]
    if missing_gates:
        raise ValueError(
            "cannot accept review while required gates are not PASS: " + ", ".join(missing_gates)
        )
    if not summary.strip():
        raise ValueError("review summary is required")
    if not next_action.strip():
        raise ValueError("review next_action is required")

    refs = [item for item in (evidence_refs or []) if item.strip()]
    checkpoints = lane.setdefault("checkpoints", [])
    seq = int(checkpoints[-1]["seq"]) + 1 if checkpoints else 1
    checkpoint = {
        "seq": seq,
        "at": _iso(now),
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "summary": summary.strip(),
        "decisions": ["Main/Reviewer accepted the implementation/review gate."],
        "evidence_refs": refs,
        "next_action": next_action.strip(),
        "kind": "REVIEW_ACCEPTED",
    }
    checkpoints.append(checkpoint)
    lane["checkpoints"] = checkpoints[-50:]
    lane["last_checkpoint"] = checkpoint
    lane.setdefault("review_history", []).append({
        "reviewed_at": _iso(now),
        "reviewed_by": "main-reviewer",
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "decision": "APPROVED",
        "summary": summary.strip(),
        "evidence_refs": refs,
    })
    lane["review_history"] = lane["review_history"][-20:]
    events = lane.setdefault("reconciliation_events", [])
    events.append({
        "type": "CLAIM_RELEASED_AFTER_REVIEW",
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "reason": "Main/Reviewer accepted the bounded implementation/review gate.",
        "at": _iso(now),
    })
    lane["reconciliation_events"] = events[-20:]
    lane["active_claim"] = None
    roadmap_material = bool((packet.get("roadmap_impact") or {}).get("material"))
    lane["status"] = "BLOCKED" if roadmap_material else "READY"
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    lane.setdefault("reviewer", {}).update({
        "state": "APPROVED",
        "reviewed_by": "main-reviewer",
        "reviewed_at": _iso(now),
    })
    lane.setdefault("gates", {})["G6_REVIEWER"] = "PASS"
    lane["gates"]["G7_CANONICAL_SYNC"] = (
        "PASS" if not roadmap_material else "PENDING_ROADMAP_SYNC"
    )
    if roadmap_material:
        roadmap_refs = list((packet.get("roadmap_impact") or {}).get("refs") or [])
        lane["block_reason"] = {
            "code": "CANONICAL_SYNC_REQUIRED",
            "roadmap_refs": roadmap_refs,
            "reviewed_claim_id": claim_data.get("claim_id"),
            "work_item": claim_data.get("work_item"),
            "detected_at": _iso(now),
        }
        lane["next_action"] = "Synchronize the material roadmap refs, then record canonical sync completion before new work can be claimed."
    else:
        lane.pop("block_reason", None)
        lane["next_action"] = next_action.strip()
    _write(lane_path, lane)
    project(root=root, now=now)



def canonical_sync_complete(
    lane_id: str,
    *,
    refs: list[str],
    root: Path = ROOT,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    _, canonical = _canonical(root)
    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    block = lane.get("block_reason") or {}
    if lane.get("status") != "BLOCKED" or block.get("code") != "CANONICAL_SYNC_REQUIRED":
        raise ValueError(f"lane {lane_id} is not blocked on canonical sync")
    clean_refs = [item.strip() for item in refs if item and item.strip()]
    if not clean_refs:
        raise ValueError("canonical sync completion requires at least one synchronized ref")
    expected_refs = set(block.get("roadmap_refs") or [])
    if expected_refs and not expected_refs.issubset(set(clean_refs)):
        missing = sorted(expected_refs - set(clean_refs))
        raise ValueError("canonical sync refs missing required roadmap refs: " + ", ".join(missing))

    lane.setdefault("gates", {})["G7_CANONICAL_SYNC"] = "PASS"
    lane["status"] = "READY"
    lane.pop("block_reason", None)
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    events = lane.setdefault("reconciliation_events", [])
    events.append({
        "type": "CANONICAL_SYNC_COMPLETED",
        "refs": clean_refs,
        "at": _iso(now),
    })
    lane["reconciliation_events"] = events[-20:]
    _write(lane_path, lane)
    project(root=root, now=now)

def review_rework(
    lane_id: str,
    *,
    reason: str,
    next_action: str,
    root: Path = ROOT,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    _, canonical = _canonical(root)
    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    if lane.get("role") == "reviewer":
        raise ValueError("reviewer lane cannot review itself")
    if lane.get("status") != "REVIEW_REQUIRED":
        raise ValueError(f"lane {lane_id} must be REVIEW_REQUIRED; current={lane.get('status')}")
    claim_data = lane.get("active_claim")
    if not claim_data:
        raise ValueError(f"lane {lane_id} REVIEW_REQUIRED has no active claim")
    _validate_review_packet(lane_id, claim_data, lane.get("review_packet") or {})
    if not reason.strip():
        raise ValueError("review rework reason is required")
    if not next_action.strip():
        raise ValueError("review rework next_action is required")

    checkpoints = lane.setdefault("checkpoints", [])
    seq = int(checkpoints[-1]["seq"]) + 1 if checkpoints else 1
    checkpoint = {
        "seq": seq,
        "at": _iso(now),
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "summary": reason.strip(),
        "decisions": ["Main/Reviewer requested bounded rework."],
        "evidence_refs": [],
        "next_action": next_action.strip(),
        "kind": "REVIEW_REWORK",
    }
    checkpoints.append(checkpoint)
    lane["checkpoints"] = checkpoints[-50:]
    lane["last_checkpoint"] = checkpoint
    lane.setdefault("review_history", []).append({
        "reviewed_at": _iso(now),
        "reviewed_by": "main-reviewer",
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "decision": "CHANGES_REQUESTED",
        "summary": reason.strip(),
    })
    lane["review_history"] = lane["review_history"][-20:]
    lane["status"] = "IMPLEMENTING"
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    lane.setdefault("reviewer", {}).update({
        "state": "CHANGES_REQUESTED",
        "reviewed_by": "main-reviewer",
        "reviewed_at": _iso(now),
    })
    lane.setdefault("gates", {})["G6_REVIEWER"] = "PENDING"
    lane["next_action"] = next_action.strip()
    _write(lane_path, lane)
    project(root=root, now=now)


def submit_review(
    lane_id: str,
    packet_path: Path,
    *,
    root: Path = ROOT,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    _, canonical = _canonical(root)
    lane_path, lane = _lane_by_id(root, canonical, lane_id)

    if lane.get("role") == "reviewer":
        raise ValueError("reviewer lane does not submit worker review packets")
    claim_data = lane.get("active_claim")
    if not claim_data:
        raise ValueError(f"lane {lane_id} has no active claim")
    _assert_claim_live(claim_data, now)
    if lane.get("status") not in {"CLAIMED", "IMPLEMENTING", "EVIDENCE_READY"}:
        raise ValueError(f"lane {lane_id} cannot submit review from state {lane.get('status')}")

    packet = _load(packet_path)
    _validate_review_packet(lane_id, claim_data, packet)

    final_next_action = "Main/Reviewer must inspect the review_packet, linked evidence and required gates before promotion or rework."
    checkpoints = lane.setdefault("checkpoints", [])
    seq = int(checkpoints[-1]["seq"]) + 1 if checkpoints else 1
    final_checkpoint = {
        "seq": seq,
        "at": _iso(now),
        "claim_id": claim_data.get("claim_id"),
        "work_item": claim_data.get("work_item"),
        "summary": packet["summary"],
        "decisions": [],
        "evidence_refs": [str(item.get("ref")) for item in packet["evidence"] if item.get("ref")],
        "next_action": final_next_action,
        "kind": "REVIEW_HANDOFF",
    }
    checkpoints.append(final_checkpoint)
    lane["checkpoints"] = checkpoints[-50:]
    lane["last_checkpoint"] = final_checkpoint
    lane["review_packet"] = packet
    lane["evidence"] = packet["evidence"]
    lane["status"] = "REVIEW_REQUIRED"
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    lane.setdefault("reviewer", {})["state"] = "PENDING"
    lane["next_action"] = final_next_action
    _write(lane_path, lane)
    project(root=root, now=now)


def reconcile(root: Path = ROOT, now: datetime | None = None) -> list[str]:
    now = now or _now()
    _, canonical = _canonical(root)
    changed: list[str] = []

    for lane_path, lane in _lanes(root, canonical):
        claim_data = lane.get("active_claim")
        if not claim_data:
            continue
        lease_until = claim_data.get("lease_until")
        if not lease_until:
            continue
        if _parse_iso(str(lease_until)) > now:
            continue

        if lane.get("status") == "REVIEW_REQUIRED":
            packet = lane.get("review_packet") or {}
            try:
                _validate_review_packet(str(lane.get("id")), claim_data, packet)
            except ValueError:
                pass
            else:
                events = lane.setdefault("reconciliation_events", [])
                already_recorded = any(
                    item.get("type") == "REVIEW_WAIT_OVERDUE"
                    and item.get("claim_id") == claim_data.get("claim_id")
                    for item in events
                )
                if not already_recorded:
                    events.append({
                        "type": "REVIEW_WAIT_OVERDUE",
                        "claim_id": claim_data.get("claim_id"),
                        "work_item": claim_data.get("work_item"),
                        "lease_until": lease_until,
                        "detected_at": _iso(now),
                        "review_required": True,
                    })
                    lane["reconciliation_events"] = events[-20:]
                    lane["updated_at"] = _date(now)
                    lane["state_version"] = int(lane.get("state_version", 0)) + 1
                    _write(lane_path, lane)
                    changed.append(str(lane_path.relative_to(root)))
                continue

        event = {
            "type": "CLAIM_LEASE_EXPIRED",
            "claim_id": claim_data.get("claim_id"),
            "work_item": claim_data.get("work_item"),
            "lease_until": lease_until,
            "detected_at": _iso(now),
        }
        events = lane.setdefault("reconciliation_events", [])
        events.append(event)
        lane["reconciliation_events"] = events[-20:]
        lane["block_reason"] = {
            "code": "CLAIM_LEASE_EXPIRED",
            "work_item": claim_data.get("work_item"),
            "claim_id": claim_data.get("claim_id"),
            "lease_until": lease_until,
            "detected_at": _iso(now),
            "review_required": True,
        }
        lane["active_claim"] = None
        lane["status"] = "BLOCKED"
        lane["updated_at"] = _date(now)
        lane["state_version"] = int(lane.get("state_version", 0)) + 1
        if lane.get("role") != "reviewer":
            lane.setdefault("reviewer", {})["state"] = "PENDING"
        _write(lane_path, lane)
        changed.append(str(lane_path.relative_to(root)))

    if project(root=root, now=now):
        changed.append(str(CANONICAL_REL))
    return changed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage canonical control-plane claims and projection.")
    sub = parser.add_subparsers(dest="command", required=True)

    claim_cmd = sub.add_parser("claim")
    claim_cmd.add_argument("--lane", required=True)
    claim_cmd.add_argument("--work-item", required=True)
    claim_cmd.add_argument("--repository", required=True)
    claim_cmd.add_argument("--scope", required=True)
    claim_cmd.add_argument("--branch")
    claim_cmd.add_argument("--lease-hours", type=int)

    hb_cmd = sub.add_parser("heartbeat")
    hb_cmd.add_argument("--lane", required=True)
    hb_cmd.add_argument("--lease-hours", type=int)

    release_cmd = sub.add_parser("release")
    release_cmd.add_argument("--lane", required=True)
    release_cmd.add_argument("--reason", required=True)

    submit_cmd = sub.add_parser("submit-review")
    submit_cmd.add_argument("--lane", required=True)
    submit_cmd.add_argument("--packet", required=True, type=Path)

    sub.add_parser("review-inbox")

    accept_cmd = sub.add_parser("review-accept")
    accept_cmd.add_argument("--lane", required=True)
    accept_cmd.add_argument("--summary", required=True)
    accept_cmd.add_argument("--next-action", required=True)
    accept_cmd.add_argument("--evidence-ref", action="append", default=[])

    rework_cmd = sub.add_parser("review-rework")
    rework_cmd.add_argument("--lane", required=True)
    rework_cmd.add_argument("--reason", required=True)
    rework_cmd.add_argument("--next-action", required=True)

    sync_cmd = sub.add_parser("canonical-sync-complete")
    sync_cmd.add_argument("--lane", required=True)
    sync_cmd.add_argument("--ref", action="append", default=[], required=True)

    sub.add_parser("reconcile")
    sub.add_parser("project")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "claim":
        claim_id = claim(
            args.lane,
            args.work_item,
            args.repository,
            args.scope,
            branch=args.branch,
            lease_hours=args.lease_hours,
        )
        print(claim_id)
    elif args.command == "heartbeat":
        print(heartbeat(args.lane, lease_hours=args.lease_hours))
    elif args.command == "release":
        release(args.lane, reason=args.reason)
        print("released")
    elif args.command == "submit-review":
        submit_review(args.lane, args.packet)
        print("review-required")
    elif args.command == "review-inbox":
        print(json.dumps(review_inbox(), indent=2, ensure_ascii=False))
    elif args.command == "review-accept":
        review_accept(
            args.lane,
            summary=args.summary,
            next_action=args.next_action,
            evidence_refs=args.evidence_ref,
        )
        print("review-accepted")
    elif args.command == "review-rework":
        review_rework(
            args.lane,
            reason=args.reason,
            next_action=args.next_action,
        )
        print("review-rework")
    elif args.command == "canonical-sync-complete":
        canonical_sync_complete(args.lane, refs=args.ref)
        print("canonical-sync-complete")
    elif args.command == "reconcile":
        changed = reconcile()
        print("\n".join(changed) if changed else "no changes")
    elif args.command == "project":
        print("updated" if project() else "no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
