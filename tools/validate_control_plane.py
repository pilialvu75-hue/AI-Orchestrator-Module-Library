#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CP = ROOT / ".airlab" / "control-plane"
ALLOWED = {"READY","CLAIMED","IMPLEMENTING","EVIDENCE_READY","REVIEW_REQUIRED","VERIFIED","DONE","BLOCKED","PAUSED"}
WORKER_MAX = {"READY","CLAIMED","IMPLEMENTING","EVIDENCE_READY","REVIEW_REQUIRED","BLOCKED","PAUSED"}

def load(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def validate(root=ROOT):
    errors = []
    canonical = load(root / ".airlab/control-plane/canonical-state.json")
    gates = load(root / ".airlab/control-plane/gates.json")
    if canonical.get("schema_version") != 1:
        errors.append("canonical-state schema_version must be 1")
    if gates.get("schema_version") != 1:
        errors.append("gates schema_version must be 1")
    paths = canonical.get("workstreams") or []
    seen_ids = set()
    active_claims = {}
    for rel in paths:
        p = root / rel
        if not p.exists():
            errors.append(f"missing workstream: {rel}")
            continue
        lane = load(p)
        lane_id = lane.get("id")
        if not lane_id:
            errors.append(f"{rel}: missing id")
            continue
        if lane_id in seen_ids:
            errors.append(f"duplicate workstream id: {lane_id}")
        seen_ids.add(lane_id)
        state = lane.get("status")
        if state not in ALLOWED:
            errors.append(f"{lane_id}: invalid status {state}")
        role = lane.get("role")
        if role != "reviewer" and state not in WORKER_MAX:
            reviewer = lane.get("reviewer") or {}
            if reviewer.get("state") != "APPROVED":
                errors.append(f"{lane_id}: worker cannot be {state} without reviewer APPROVED")
        if lane_id.startswith("platform-") and lane.get("shared_engine_policy") != "adapter_only":
            errors.append(f"{lane_id}: platform lane must use adapter_only shared engine policy")
        claim = lane.get("active_claim")
        if claim:
            key = claim.get("work_item")
            if not key:
                errors.append(f"{lane_id}: active_claim missing work_item")
            elif key in active_claims:
                errors.append(f"duplicate active claim {key}: {active_claims[key]} and {lane_id}")
            else:
                active_claims[key] = lane_id
            for field in ("repository","started_at","scope"):
                if not claim.get(field):
                    errors.append(f"{lane_id}: active_claim missing {field}")
        if state in {"VERIFIED","DONE"} and not lane.get("evidence"):
            errors.append(f"{lane_id}: {state} requires evidence")
        if state == "DONE":
            gs = lane.get("gates") or {}
            for gate in ("G0_CLAIM","G1_IMPLEMENTATION","G2_STATIC","G3_CI","G4_INTEGRATION","G6_REVIEWER","G7_CANONICAL_SYNC"):
                if gs.get(gate) != "PASS":
                    errors.append(f"{lane_id}: DONE requires {gate}=PASS")
    if canonical.get("promotion_policy",{}).get("worker_max_state") != "REVIEW_REQUIRED":
        errors.append("canonical promotion_policy.worker_max_state must be REVIEW_REQUIRED")
    return errors

if __name__ == "__main__":
    problems = validate()
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        raise SystemExit(1)
    print("Canonical control plane validation: PASS")
