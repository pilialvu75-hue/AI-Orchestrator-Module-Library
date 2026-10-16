"""Read-only chat supervision snapshot from the single canonical authority.

The chat is an optional control interface, never the autonomous worker runtime.
No user suggestion may be silently promoted to a canonical mutation.
"""
import argparse
import json
from pathlib import Path


def snapshot(root, lane_id):
    root = Path(root)
    registry = json.loads((root / ".airlab/control-plane/chat-registry.json").read_text(encoding="utf-8"))
    canonical = json.loads((root / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
    chat = next((x for x in registry.get("lanes", []) if x.get("id") == lane_id), None)
    if chat is None:
        raise ValueError("unknown chat lane: " + lane_id)
    lane = None
    for relative in canonical.get("workstreams", []):
        state = json.loads((root / relative).read_text(encoding="utf-8"))
        if state.get("id") == lane_id:
            lane = state
            break
    if lane is None:
        raise ValueError("chat lane missing from canonical workstreams")
    return {
        "schema_version": 1,
        "lane_id": lane_id,
        "chat_title": chat["chat_title"],
        "canonical_state_version": lane["state_version"],
        "status": lane.get("status"),
        "active_claim": lane.get("active_claim"),
        "next_action": lane.get("next_action"),
        "last_checkpoint": lane.get("last_checkpoint"),
        "review_packet": lane.get("review_packet"),
        "supervision": {
            "status_read": True,
            "suggestion_requires_explicit_review": True,
            "roadmap_change_requires_owner_decision": True,
            "other_lanes_continue": True,
            "chat_is_execution_engine": False,
        },
        "mutated": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--lane", required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.root, args.lane), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
