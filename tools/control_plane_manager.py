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


def _lanes_isolated(
    root: Path,
    canonical: dict[str, Any],
) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, Any]]]:
    lanes: list[tuple[Path, dict[str, Any]]] = []
    incidents: list[dict[str, Any]] = []
    for path in _lane_paths(root, canonical):
        try:
            lane = _load(path)
        except Exception as error:
            incidents.append({
                "path": str(path.relative_to(root)),
                "code": "LANE_UNREADABLE",
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        if not isinstance(lane, dict):
            incidents.append({
                "path": str(path.relative_to(root)),
                "code": "LANE_INVALID_ROOT",
                "error": "lane root must be an object",
            })
            continue
        lanes.append((path, lane))
    return lanes, incidents


def _lane_by_id(root: Path, canonical: dict[str, Any], lane_id: str) -> tuple[Path, dict[str, Any]]:
    lanes, incidents = _lanes_isolated(root, canonical)
    for path, lane in lanes:
        if lane.get("id") == lane_id:
            return path, lane
    incident_paths = ", ".join(item["path"] for item in incidents)
    suffix = f"; unreadable workstreams={incident_paths}" if incident_paths else ""
    raise ValueError(f"unknown or unreadable lane: {lane_id}{suffix}")


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


def _normalize_resource_locks(
    resource_locks: list[str] | None,
    *,
    repository: str,
    branch: str | None,
) -> list[str]:
    if resource_locks is None:
        resource_locks = []
    if not isinstance(resource_locks, list):
        raise ValueError("resource_locks must be a list of strings")

    normalized: list[str] = []
    for index, item in enumerate(resource_locks):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"resource_locks[{index}] must be a non-empty string")
        key = item.strip()
        if len(key) > 256:
            raise ValueError(f"resource_locks[{index}] exceeds 256 characters")
        if ":" not in key:
            raise ValueError(
                f"resource_locks[{index}] must use a namespace:value key, got {key!r}"
            )
        normalized.append(key)

    if branch is not None:
        if not isinstance(branch, str) or not branch.strip():
            raise ValueError("branch must be a non-empty string or null")
        normalized.append(f"branch:{repository}:{branch.strip()}")

    unique = sorted(set(normalized))
    if len(unique) > 64:
        raise ValueError("resource_locks may contain at most 64 unique keys")
    return unique


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
    projection_incidents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    active_claims: list[dict[str, Any]] = []
    active_resource_locks: list[dict[str, Any]] = []
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
                "resource_locks": list(claim.get("resource_locks") or []),
            }
            active_claims.append({"lane": lane_id, **claim_summary})
            for lock_key in claim_summary["resource_locks"]:
                active_resource_locks.append({
                    "key": lock_key,
                    "lane": lane_id,
                    "claim_id": claim.get("claim_id"),
                    "work_item": claim.get("work_item"),
                })

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
        "active_resource_locks": sorted(
            active_resource_locks,
            key=lambda item: (str(item.get("key") or ""), str(item.get("lane") or "")),
        ),
        "review_required": sorted(review_required),
        "blocked": sorted(blocked, key=lambda item: item["lane"]),
        "checkpoint_watch": sorted(checkpoint_watch, key=lambda item: item["lane"]),
        "projection_incidents": sorted(
            projection_incidents or [],
            key=lambda item: (str(item.get("path") or ""), str(item.get("code") or "")),
        ),
        "platform_inference_profiles": sorted(platform_profiles, key=lambda item: item["lane"]),
        "lanes": summaries,
    }


def project(root: Path = ROOT, now: datetime | None = None) -> bool:
    now = now or _now()
    canonical_path, canonical = _canonical(root)
    checkpoint_warning_minutes = _checkpoint_watch_policy(canonical)
    lanes, incidents = _lanes_isolated(root, canonical)
    payload = _projection_payload(
        lanes,
        now=now,
        checkpoint_warning_minutes=checkpoint_warning_minutes,
        projection_incidents=incidents,
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
    resource_locks: list[str] | None = None,
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
    lock_keys = _normalize_resource_locks(
        resource_locks,
        repository=repository.strip(),
        branch=branch,
    )
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
        if not other_claim:
            continue
        if other_claim.get("work_item") == work_item:
            raise ValueError(f"work_item already claimed by {other.get('id')}: {work_item}")
        other_locks = other_claim.get("resource_locks") or []
        if not isinstance(other_locks, list):
            raise ValueError(f"lane {other.get('id')} has invalid active_claim resource_locks")
        overlap = sorted(set(lock_keys).intersection(other_locks))
        if overlap:
            raise ValueError(
                "resource lock conflict with "
                f"{other.get('id')} claim {other_claim.get('claim_id')}: {', '.join(overlap)}"
            )

    seed = f"{lane_id}|{work_item}|{_iso(now)}"
    claim_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    lease_until = now + timedelta(hours=hours)

    previous_packet = lane.pop("review_packet", None)
    if previous_packet:
        history = lane.setdefault("review_packet_history", [])
        history.append(previous_packet)
        lane["review_packet_history"] = history[-20:]
    lane["evidence"] = []
    # Claim-bound manual or autonomous gate evidence must never be carried into
    # a different work item; its digest only attests the previous review packet.
    lane.pop("current_gate_attestation", None)
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
        "resource_locks": lock_keys,
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


def _review_packet_digest(packet: dict[str, Any]) -> str:
    """Stable fingerprint of the entire claim-bound review packet."""
    canonical = json.dumps(packet, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reset_review_gate_attestation(lane: dict[str, Any]) -> None:
    # Review evidence belongs to one exact packet, never to a claim forever.
    for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
        lane.setdefault("gates", {})[gate] = "PENDING"
    lane.pop("current_gate_attestation", None)


def _review_gate_passed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("PASS")



def validate_autonomous_completion(
    lane: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read-only fail-closed eligibility check; never grants reviewer approval.

    This is a prerequisite for a future transactional inbox operation, not
    an authorization to mutate canonical state or merge a pull request.
    """
    now = now or _now()
    if lane.get("role") != "worker":
        raise ValueError("autonomous completion is limited to worker lanes")
    if lane.get("status") != "REVIEW_REQUIRED":
        raise ValueError("worker has not submitted its evidence packet")
    claim_data = lane.get("active_claim")
    if not isinstance(claim_data, dict):
        raise ValueError("active claim is required")
    _assert_claim_live(claim_data, now)
    packet = lane.get("review_packet")
    if not isinstance(packet, dict):
        raise ValueError("claim-bound evidence packet is required")
    _validate_review_packet(str(lane.get("id")), claim_data, packet)
    gates = lane.get("gates") or {}
    required = ("G0_CLAIM", "G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION")
    missing = [gate for gate in required if not _review_gate_passed(gates.get(gate))]
    if missing:
        raise ValueError("required evidence gates are not PASS: " + ", ".join(missing))
    attestation = lane.get("current_gate_attestation") or {}
    digest = _review_packet_digest(packet)
    if attestation.get("claim_id") != claim_data.get("claim_id") or attestation.get("packet_sha256") != digest:
        raise ValueError("missing or stale packet-bound evidence attestation")
    # A worker-authored packet is not an independent verification of its own gates.
    # Only a separately attested verifier may authorize eventual completion.
    verifier = attestation.get("reviewed_by") or attestation.get("verified_by")
    if not isinstance(verifier, str) or not verifier.strip():
        raise ValueError("independent gate verifier identity is required")
    if verifier in {str(lane.get("id")), f"chatgpt:{lane.get('id')}"}:
        raise ValueError("worker cannot attest its own completion gates")
    # This preflight cannot authenticate arbitrary actor labels stored in lane JSON.
    # Trusted receipts must be validated outside the worker-writable state.
    # Explicitly exclude reviewer attestations from the new autonomous route.
    # A separate CI-backed verifier will eventually issue its own receipt.
    if verifier == "main-reviewer" or verifier == "chatgpt:main-reviewer":
        raise ValueError("manual reviewer attestation is not autonomous evidence")
    # Identity labels are user-controlled metadata, not cryptographic provenance.
    # Until an inbox-side trusted verifier writes a receipt, fail closed.
    if attestation.get("trusted_verifier_receipt") is not True:
        raise ValueError("trusted independent verifier receipt is required")
    # Check the target runtime gate even while trusted receipt verification is
    # unavailable. This keeps preflight diagnostics meaningful and ensures
    # runtime gaps cannot be hidden behind the provenance blocker.
    runtime_gate = gates.get("G5_TARGET_RUNTIME")
    if runtime_gate not in ("NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE", "NOT_APPLICABLE"):
        if not _review_gate_passed(runtime_gate):
            raise ValueError("target runtime evidence is required or unresolved")
    if type(lane.get("state_version")) is not int or lane["state_version"] < 0:
        raise ValueError("state version is required for transactional mutation")
    # A receipt flag in mutable lane JSON is NOT proof of provenance. Until
    # receipt verification is implemented against a protected external source,
    # this API must never advertise eligibility for automatic state changes.
    raise ValueError("autonomous completion disabled: trusted receipt provenance is not verified")


def complete_verified_library_needs(
    lane_id: str,
    *,
    identity: dict[str, Any],
    verified_scope: dict[str, Any],
    protected_run: dict[str, Any],
    verified_ci_audit: dict[str, Any],
    root: Path = ROOT,
    now: datetime | None = None,
) -> None:
    """Release one independently verified *metadata-only* Library claim.

    The caller MUST be the transactional inbox, which fetches the protected
    run and revalidates both GitHub CI and the exact PR diff. These arguments
    are not a worker-accessible authorization interface.
    """
    now = now or _now()
    if lane_id != "library-curation":
        raise ValueError("autonomous fast path restricted to the Library worker lane")
    _, canonical = _canonical(root)
    lane_path, lane = _lane_by_id(root, canonical, lane_id)
    if lane.get("role") != "worker" or lane.get("status") != "REVIEW_REQUIRED":
        raise ValueError("autonomous needs completion requires REVIEW_REQUIRED worker")
    claim = lane.get("active_claim")
    packet = lane.get("review_packet")
    if not isinstance(claim, dict) or not isinstance(packet, dict):
        raise ValueError("autonomous needs completion requires claim and packet")
    _assert_claim_live(claim, now)
    _validate_review_packet(lane_id, claim, packet)
    expected_identity = {
        "lane_id": lane_id,
        "state_version": lane.get("state_version"),
        "claim_id": claim.get("claim_id"),
        "packet_sha256": _review_packet_digest(packet),
        "repository": claim.get("repository"),
        "pr_number": packet.get("pull_request"),
        "head_sha": identity.get("head_sha") if isinstance(identity, dict) else None,
    }
    if not isinstance(identity, dict) or identity != expected_identity:
        raise ValueError("stale or forged canonical autonomous receipt identity")
    from tools.autonomous_receipt_binding import validate_receipt_binding
    validate_receipt_binding(identity, expected_identity)
    if (not isinstance(verified_scope, dict)
            or verified_scope.get("profile") != "library-needs-only-v1"
            or verified_scope.get("canonical_identity") != identity
            or verified_scope.get("scope_verified") is not True
            or verified_scope.get("runtime_applicable") is not False
            or verified_scope.get("executable_changes") is not False
            or verified_scope.get("changed_file") != "catalog/needs.json"):
        raise ValueError("independently verified needs-only scope required")
    if (not isinstance(protected_run, dict)
            or protected_run.get("repository") != identity["repository"]
            or type(protected_run.get("run_id")) is not int
            or protected_run.get("workflow_path") != ".github/workflows/autonomous-ci-probe.yml"):
        raise ValueError("protected workflow provenance is required")
    if (not isinstance(verified_ci_audit, dict)
            or verified_ci_audit.get("canonical_identity") != identity
            or verified_ci_audit.get("trusted_receipt") is not False
            or verified_ci_audit.get("completion_authorized") is not False
            or not isinstance(verified_ci_audit.get("gate_assessment"), dict)
            or verified_ci_audit["gate_assessment"].get("G2_STATIC") != "CI_PIPELINE_STEPS_VERIFIED"
            or verified_ci_audit["gate_assessment"].get("G3_CI") != "EXACT_HEAD_SUCCESS_VERIFIED"):
        raise ValueError("independently rechecked CI gate audit is required")

    if (packet.get("roadmap_impact") or {}).get("material") is not False:
        raise ValueError("material roadmap changes cannot use autonomous needs fast path")
    if any(item.get("type") in ("runtime", "physical_device")
           for item in packet.get("evidence", [])):
        raise ValueError("runtime or physical evidence claims need independent review")
    gates = lane.get("gates")
    if not isinstance(gates, dict) or gates.get("G0_CLAIM") != "PASS":
        raise ValueError("live canonical claim gate G0 must already be PASS")
    if gates.get("G5_TARGET_RUNTIME") not in (
        "NOT_APPLICABLE", "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE"
    ):
        raise ValueError("autonomous needs scope cannot override an unresolved runtime gate")
    if gates.get("G6_REVIEWER") != "PENDING":
        raise ValueError("autonomous completion may not reuse or forge G6 reviewer approval")
    if (lane.get("reviewer") or {}).get("state") == "APPROVED":
        raise ValueError("autonomous completion cannot replace a recorded human review")

    at = _iso(now)
    audit_ref = (
        f"https://github.com/{identity['repository']}/actions/runs/"
        f"{verified_ci_audit['workflow_run_id']}"
    )
    lane["current_gate_attestation"] = {
        "at": at,
        "claim_id": identity["claim_id"],
        "packet_sha256": identity["packet_sha256"],
        "verified_by": "protected-library-needs-v1",
        "summary": "Needs-only metadata scope, exact-head CI and offline snapshot validated independently.",
        "evidence_refs_by_gate": {
            gate: [audit_ref]
            for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION")
        },
    }
    lane.setdefault("gate_evidence_history", []).append(lane["current_gate_attestation"])
    lane["gate_evidence_history"] = lane["gate_evidence_history"][-20:]
    for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
        gates[gate] = "PASS"
    gates["G7_CANONICAL_SYNC"] = "PASS"
    # G6 stays PENDING; do NOT write review_history/APPROVED.
    lane.setdefault("autonomous_completion_history", []).append({
        "at": at,
        "claim_id": identity["claim_id"],
        "work_item": claim["work_item"],
        "profile": "library-needs-only-v1",
        "identity": identity,
        "protected_run_id": protected_run["run_id"],
        "ci_run_id": verified_ci_audit["workflow_run_id"],
        "scope_blob_sha": verified_scope["file_blob_sha"],
        "decision": "VERIFIED_METADATA_ONLY",
    })
    lane["autonomous_completion_history"] = lane["autonomous_completion_history"][-20:]
    lane.setdefault("reconciliation_events", []).append({
        "type": "CLAIM_RELEASED_AFTER_AUTONOMOUS_NEEDS_VERIFICATION",
        "claim_id": identity["claim_id"],
        "work_item": claim["work_item"],
        "at": at,
    })
    lane["reconciliation_events"] = lane["reconciliation_events"][-20:]
    lane["active_claim"] = None
    lane["status"] = "READY"
    lane["state_version"] += 1
    lane["updated_at"] = _date(now)
    lane.pop("block_reason", None)
    lane["next_action"] = (
        "Claim the next bounded Library task. Executable module certification "
        "still requires independent implementation/integration/runtime evidence."
    )
    _write(lane_path, lane)
    project(root=root, now=now)


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
    # Every gate pass must have an evidence attestation for this exact packet.
    # Old gate values alone are not an acceptable substitute for new evidence.
    current = lane.get("current_gate_attestation") or {}
    if (current.get("claim_id") != claim_data.get("claim_id")
            or current.get("packet_sha256") != _review_packet_digest(packet)):
        raise ValueError("review gate evidence is missing or stale for current review packet")
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
    _reset_review_gate_attestation(lane)
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
    _reset_review_gate_attestation(lane)

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
    lanes, _ = _lanes_isolated(root, canonical)

    for lane_path, lane in lanes:
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
            "resource_locks": list(claim_data.get("resource_locks") or []),
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
            "resource_locks": list(claim_data.get("resource_locks") or []),
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
    claim_cmd.add_argument("--resource-lock", action="append", default=[])
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
            resource_locks=args.resource_lock,
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
