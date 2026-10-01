#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CP = ROOT / ".airlab" / "control-plane"


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def registry(root: Path = ROOT) -> dict[str, Any]:
    return load(root / ".airlab/control-plane/chat-registry.json")


def lane_entry(lane_id: str, root: Path = ROOT) -> dict[str, Any]:
    for entry in registry(root).get("lanes", []):
        if entry.get("id") == lane_id:
            return entry
    raise ValueError(f"unknown chat lane: {lane_id}")


def lane_state(lane_id: str, root: Path = ROOT) -> dict[str, Any]:
    canonical = load(root / ".airlab/control-plane/canonical-state.json")
    for rel in canonical.get("workstreams", []):
        path = root / rel
        lane = load(path)
        if lane.get("id") == lane_id:
            return lane
    raise ValueError(f"workstream not found: {lane_id}")


def build_prompt(lane_id: str, root: Path = ROOT) -> str:
    entry = lane_entry(lane_id, root)
    lane = lane_state(lane_id, root)
    mode = entry["mode"]
    repo = entry["primary_repository"]
    secondary = entry.get("secondary_repositories") or []
    secondary_text = "\n".join(f"- {item}" for item in secondary) or "- none"

    common = f"""RELAY CANONICO — {entry['chat_title']}

LANE_ID: {lane_id}
ROLE_MODE: {mode}
PRIMARY_REPOSITORY: {repo}
SECONDARY_REPOSITORIES:
{secondary_text}

PURPOSE:
{entry['purpose']}

AUTHORITATIVE CONTROL PLANE:
pilialvu75-hue/AI-Orchestrator-Module-Library

MANDATORY START:
1. Read .airlab/handoff.md in AI-Orchestrator-Module-Library.
2. Read .airlab/control-plane/canonical-state.json.
3. Read .airlab/control-plane/gates.json.
4. Read .airlab/control-plane/workstreams/{lane_id}.json.
5. Read the relevant private roadmap and current repository PR/issues/CI/Diagnostics evidence.
6. Treat repository canonical state as authoritative over conversational memory or old relay text.

CURRENT LANE STATE:
status={lane.get('status')}
activation={lane.get('activation')}
state_version={lane.get('state_version')}
scope={lane.get('scope')}
active_claim={json.dumps(lane.get('active_claim'), ensure_ascii=False)}
last_checkpoint={json.dumps(lane.get('last_checkpoint'), ensure_ascii=False)}

OPERATING RULES:
- Do not restart from a generic audit when a bounded next action already exists.
- Before implementation, hold a unique non-expired canonical claim for one bounded work_item.
- Do not duplicate another active claim.
- Keep the claim heartbeat current during long work.
- Persist a canonical checkpoint after every material milestone, decision, newly discovered blocker, merged/closed PR, physical/runtime result, or change to the next action.
- Do not wait for the chat to become full. Use tools/chat_checkpoint.py while working; a checkpoint also renews the active claim lease.
- Before a long/high-risk step, checkpoint the current safe resume point.
- CI green is only one gate and never proves runtime/hardware behavior by itself.
- Record evidence as work advances.
- Update the affected roadmap/state when accepted evidence materially changes scope, priority, dependency or completion.
"""

    if mode == "reviewer":
        specific = """
MAIN / REVIEWER RULES:
- You are the cross-lane reviewer and canonical promotion authority.
- Inspect worker lanes in REVIEW_REQUIRED, their PRs, CI, Diagnostics/runtime evidence and roadmap impact.
- Strengthen weak work instead of merely summarizing it.
- Detect duplicated work, stale assumptions, cross-platform regressions and contract drift.
- Only promote VERIFIED/DONE when required gates and evidence are actually satisfied.
- UNKNOWN remains UNKNOWN; do not infer PASS.
- Reconcile BLOCKED stale claims explicitly before allowing reassignment.
- Inspect canonical checkpoint_watch and follow up on claimed lanes that have not persisted progress recently.
- For inference, preserve shared contracts while allowing target-specific LLM/backend/runtime profiles.
"""
    else:
        specific = """
WORKER RULES:
- You may implement, test and collect evidence only inside this lane's scope.
- Your maximum self-declared state is REVIEW_REQUIRED.
- Do not self-promote VERIFIED or DONE.
- When implementation is ready, attach a review_packet conforming to .airlab/control-plane/schemas/review-packet.schema.json.
- Keep the active claim until Main/Reviewer accepts, rejects or explicitly releases/reconciles it.
- If work requires a shared-contract change owned by another lane, record the dependency instead of silently forking the contract.
"""
        if lane_id.startswith("platform-"):
            specific += """
PLATFORM INFERENCE RULE:
- Shared inference/routing semantics come from Runtime Core.
- This platform owns its actual benchmark-gated target profile.
- LLM family/size, quantization, backend, acceleration, context/batch/thread settings and fallbacks may differ from every other platform.
- Optimize for the strongest practical stable profile on real target hardware/software; neither overload constrained devices nor artificially limit capable hardware.
"""

    finish = """
END CONDITION:
Stop worker implementation at REVIEW_REQUIRED with structured evidence. Main/Reviewer decides VERIFIED/DONE and synchronizes canonical state.
"""
    return common + specific + finish


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the canonical bootstrap prompt for one AI Orchestrator chat lane.")
    parser.add_argument("--lane", required=True)
    args = parser.parse_args()
    print(build_prompt(args.lane))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
