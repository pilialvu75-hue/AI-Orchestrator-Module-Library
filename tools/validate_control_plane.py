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
    inference = load(root / ".airlab/control-plane/inference-policy.json")
    if canonical.get("schema_version") != 1:
        errors.append("canonical-state schema_version must be 1")
    if gates.get("schema_version") != 1:
        errors.append("gates schema_version must be 1")
    if inference.get("schema_version") != 1:
        errors.append("inference-policy schema_version must be 1")
    if inference.get("profile_selection", {}).get("no_universal_default_model") is not True:
        errors.append("inference-policy must forbid a universal default model")
    if canonical.get("inference_policy") != ".airlab/control-plane/inference-policy.json":
        errors.append("canonical state must reference inference-policy.json")
    claim_policy = canonical.get("claim_policy") or {}
    default_lease = claim_policy.get("default_lease_hours")
    max_lease = claim_policy.get("max_lease_hours")
    if not isinstance(default_lease, int) or default_lease <= 0:
        errors.append("claim_policy.default_lease_hours must be a positive integer")
    if not isinstance(max_lease, int) or max_lease < default_lease:
        errors.append("claim_policy.max_lease_hours must be >= default_lease_hours")
    if claim_policy.get("stale_action") != "BLOCKED_REQUIRES_REVIEWER":
        errors.append("stale claim action must be BLOCKED_REQUIRES_REVIEWER")
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
        if lane_id.startswith("platform-"):
            if lane.get("inference_profile_policy") != "target_owned_benchmark_gated":
                errors.append(f"{lane_id}: missing target_owned_benchmark_gated inference policy")
            profile = lane.get("inference_profile") or {}
            if profile.get("owner") != lane_id:
                errors.append(f"{lane_id}: inference profile owner must be the platform lane")
            if profile.get("shared_contract_owner") != "runtime-core":
                errors.append(f"{lane_id}: inference shared contract owner must be runtime-core")
        claim = lane.get("active_claim")
        if claim:
            key = claim.get("work_item")
            if not key:
                errors.append(f"{lane_id}: active_claim missing work_item")
            elif key in active_claims:
                errors.append(f"duplicate active claim {key}: {active_claims[key]} and {lane_id}")
            else:
                active_claims[key] = lane_id
            for field in ("claim_id","owner_lane","repository","scope","started_at","heartbeat_at","lease_until","lease_hours"):
                if not claim.get(field):
                    errors.append(f"{lane_id}: active_claim missing {field}")
            if claim.get("owner_lane") != lane_id:
                errors.append(f"{lane_id}: active_claim owner_lane mismatch")
            if state not in {"CLAIMED","IMPLEMENTING","EVIDENCE_READY","REVIEW_REQUIRED"}:
                errors.append(f"{lane_id}: active claim is inconsistent with state {state}")
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
