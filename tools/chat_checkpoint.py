#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import control_plane_manager

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def lane_path(lane_id: str, root: Path = ROOT) -> Path:
    canonical = load(root / ".airlab/control-plane/canonical-state.json")
    path, _ = control_plane_manager._lane_by_id(root, canonical, lane_id)
    return path


def checkpoint(
    lane_id: str,
    summary: str,
    next_action: str,
    *,
    decisions: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    root: Path = ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or now_utc()
    path = lane_path(lane_id, root)
    lane = load(path)
    claim = lane.get("active_claim")
    if not claim:
        raise ValueError(f"lane {lane_id} has no active claim")
    lease_until = claim.get("lease_until")
    if not lease_until:
        raise ValueError(f"lane {lane_id} active claim is missing lease_until")
    if parse_iso(str(lease_until)) <= now:
        raise ValueError(
            f"checkpoint cannot renew an expired claim ({lease_until}); reconcile/reviewer action is required"
        )
    if lane.get("status") in {"READY", "BLOCKED", "PAUSED", "VERIFIED", "DONE", "REVIEW_REQUIRED"}:
        raise ValueError(f"lane {lane_id} cannot checkpoint from state {lane.get('status')}")
    if not summary.strip():
        raise ValueError("checkpoint summary is required")
    if not next_action.strip():
        raise ValueError("checkpoint next_action is required")

    lease_hours = int(claim.get("lease_hours") or 12)
    claim["heartbeat_at"] = iso(now)
    claim["lease_until"] = iso(now + timedelta(hours=lease_hours))

    checkpoints = lane.setdefault("checkpoints", [])
    seq = int(checkpoints[-1]["seq"]) + 1 if checkpoints else 1
    entry = {
        "seq": seq,
        "at": iso(now),
        "claim_id": claim.get("claim_id"),
        "work_item": claim.get("work_item"),
        "summary": summary.strip(),
        "decisions": [item for item in (decisions or []) if item.strip()],
        "evidence_refs": [item for item in (evidence_refs or []) if item.strip()],
        "next_action": next_action.strip(),
    }
    checkpoints.append(entry)
    lane["checkpoints"] = checkpoints[-50:]
    lane["last_checkpoint"] = entry
    lane["next_action"] = entry["next_action"]
    if lane.get("status") == "CLAIMED":
        lane["status"] = "IMPLEMENTING"
    lane["updated_at"] = now.date().isoformat()
    lane["state_version"] = int(lane.get("state_version", 0)) + 1
    write(path, lane)
    control_plane_manager.project(root=root, now=now)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist a material chat-work checkpoint into canonical lane state.")
    parser.add_argument("--lane", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--next-action", required=True)
    parser.add_argument("--decision", action="append", default=[])
    parser.add_argument("--evidence-ref", action="append", default=[])
    args = parser.parse_args()
    result = checkpoint(
        args.lane,
        args.summary,
        args.next_action,
        decisions=args.decision,
        evidence_refs=args.evidence_ref,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
