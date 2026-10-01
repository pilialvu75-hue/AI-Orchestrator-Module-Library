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


def _lease_policy(canonical: dict[str, Any]) -> tuple[int, int]:
    policy = canonical.get("claim_policy") or {}
    default_hours = int(policy.get("default_lease_hours", DEFAULT_LEASE_HOURS))
    max_hours = int(policy.get("max_lease_hours", MAX_LEASE_HOURS))
    return default_hours, max_hours


def _projection_payload(lanes: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    active_claims: list[dict[str, Any]] = []
    review_required: list[str] = []
    blocked: list[dict[str, Any]] = []
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
        })

    return {
        "counts": dict(sorted(counts.items())),
        "active_claims": sorted(active_claims, key=lambda item: (item["lane"], item.get("work_item") or "")),
        "review_required": sorted(review_required),
        "blocked": sorted(blocked, key=lambda item: item["lane"]),
        "platform_inference_profiles": sorted(platform_profiles, key=lambda item: item["lane"]),
        "lanes": summaries,
    }


def project(root: Path = ROOT, now: datetime | None = None) -> bool:
    now = now or _now()
    canonical_path, canonical = _canonical(root)
    payload = _projection_payload(_lanes(root, canonical))
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
    gates = lane.setdefault("gates", {})
    gates["G0_CLAIM"] = "PASS"
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
    lane.setdefault("gates", {})["G0_CLAIM"] = "PENDING"
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
    if lane.get("status") not in {"CLAIMED", "IMPLEMENTING", "EVIDENCE_READY"}:
        raise ValueError(f"lane {lane_id} cannot submit review from state {lane.get('status')}")

    packet = _load(packet_path)
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
    if not packet.get("changes"):
        raise ValueError("review packet requires at least one change")
    if not packet.get("evidence"):
        raise ValueError("review packet requires at least one evidence item")
    if not packet.get("reviewer_checks"):
        raise ValueError("review packet requires reviewer_checks")

    lane["review_packet"] = packet
    lane["evidence"] = packet["evidence"]
    lane["status"] = "REVIEW_REQUIRED"
    lane["updated_at"] = _date(now)
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    lane.setdefault("reviewer", {})["state"] = "PENDING"
    lane["next_action"] = "Main/Reviewer must inspect the review_packet, linked evidence and required gates before promotion or rework."
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
    elif args.command == "reconcile":
        changed = reconcile()
        print("\n".join(changed) if changed else "no changes")
    elif args.command == "project":
        print("updated" if project() else "no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
