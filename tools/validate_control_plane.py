#!/usr/bin/env python3
import json
import control_plane_manager
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
    registry = load(root / ".airlab/control-plane/chat-registry.json")
    archive = load(root / ".airlab/control-plane/historical-chat-consolidation.json")
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
    checkpoint_watchdog = (canonical.get("continuous_checkpoint_policy") or {}).get("watchdog") or {}
    warning_minutes = checkpoint_watchdog.get("warning_after_minutes")
    if not isinstance(warning_minutes, int) or warning_minutes <= 0:
        errors.append("continuous checkpoint watchdog warning_after_minutes must be a positive integer")
    if checkpoint_watchdog.get("automatic_content_generation") is not False:
        errors.append("continuous checkpoint watchdog must not fabricate chat content")
    mutation_policy = canonical.get("mutation_policy") or {}
    if mutation_policy.get("mode") != "transactional_inbox_compare_and_swap":
        errors.append("mutation_policy.mode must be transactional_inbox_compare_and_swap")
    if mutation_policy.get("processor") != "tools/control_plane_inbox.py":
        errors.append("mutation_policy.processor must reference control_plane_inbox.py")
    if mutation_policy.get("expected_state_version_required") is not True:
        errors.append("mutation_policy must require expected_state_version")
    if mutation_policy.get("api_direct_workstream_writes") != "FORBIDDEN":
        errors.append("mutation_policy must forbid direct API workstream writes")
    if mutation_policy.get("invalid_request_behavior") != "QUARANTINE_WITHOUT_LANE_MUTATION":
        errors.append("mutation_policy invalid requests must quarantine without lane mutation")
    if mutation_policy.get("projection_failure_isolation") != "PER_LANE_INCIDENT":
        errors.append("mutation_policy must isolate projection failures per lane")

    claim_policy = canonical.get("claim_policy") or {}
    default_lease = claim_policy.get("default_lease_hours")
    max_lease = claim_policy.get("max_lease_hours")
    if not isinstance(default_lease, int) or default_lease <= 0:
        errors.append("claim_policy.default_lease_hours must be a positive integer")
    if not isinstance(max_lease, int) or max_lease < default_lease:
        errors.append("claim_policy.max_lease_hours must be >= default_lease_hours")
    if claim_policy.get("stale_action") != "BLOCKED_REQUIRES_REVIEWER":
        errors.append("stale claim action must be BLOCKED_REQUIRES_REVIEWER")
    if canonical.get("chat_registry") != ".airlab/control-plane/chat-registry.json":
        errors.append("canonical state must reference chat-registry.json")
    if registry.get("schema_version") != 1:
        errors.append("chat-registry schema_version must be 1")
    if canonical.get("chat_archive_policy", {}).get("consolidation_registry") != ".airlab/control-plane/historical-chat-consolidation.json":
        errors.append("canonical state must reference historical-chat-consolidation.json")
    if archive.get("schema_version") != 1:
        errors.append("historical-chat-consolidation schema_version must be 1")
    archive_statuses = {"DELETE_CANDIDATE","KEEP_UNTIL_REPLACED","KEEP_SEPARATE"}
    archive_titles = set()
    for entry in archive.get("chats") or []:
        title = entry.get("title")
        lane_id = entry.get("lane")
        status = entry.get("status")
        if not title:
            errors.append("historical chat entry missing title")
            continue
        if title in archive_titles:
            errors.append(f"duplicate historical chat title: {title}")
        archive_titles.add(title)
        if status not in archive_statuses:
            errors.append(f"{title}: invalid historical chat status {status}")
        if not entry.get("reason"):
            errors.append(f"{title}: historical chat entry missing reason")
        if lane_id and lane_id not in {item.get("id") for item in registry.get("lanes") or []}:
            errors.append(f"{title}: unknown canonical lane {lane_id}")
    registry_ids = set()
    for entry in registry.get("lanes") or []:
        lane_id = entry.get("id")
        if not lane_id:
            errors.append("chat-registry entry missing id")
            continue
        if lane_id in registry_ids:
            errors.append(f"duplicate chat-registry lane: {lane_id}")
        registry_ids.add(lane_id)
        if entry.get("mode") not in {"worker", "reviewer"}:
            errors.append(f"{lane_id}: chat-registry mode must be worker or reviewer")
        if not entry.get("primary_repository"):
            errors.append(f"{lane_id}: chat-registry missing primary_repository")
        if not entry.get("chat_title"):
            errors.append(f"{lane_id}: chat-registry missing chat_title")
    projection_incidents = (canonical.get("projection") or {}).get("projection_incidents") or []
    if not isinstance(projection_incidents, list):
        errors.append("canonical projection_incidents must be a list")
    else:
        for index, incident in enumerate(projection_incidents):
            if not isinstance(incident, dict):
                errors.append(f"projection_incidents[{index}] must be an object")
                continue
            if not incident.get("path") or not incident.get("code") or not incident.get("error"):
                errors.append(f"projection_incidents[{index}] requires path, code and error")

    paths = canonical.get("workstreams") or []
    seen_ids = set()
    active_claims = {}
    for rel in paths:
        p = root / rel
        if not p.exists():
            errors.append(f"missing workstream: {rel}")
            continue
        try:
            lane = load(p)
        except Exception as error:
            errors.append(f"{rel}: unreadable workstream: {type(error).__name__}: {error}")
            continue
        if not isinstance(lane, dict):
            errors.append(f"{rel}: workstream root must be an object")
            continue
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
            registry_entry = next((item for item in (registry.get("lanes") or []) if item.get("id") == lane_id), {})
            allowed_repositories = {registry_entry.get("primary_repository")}
            allowed_repositories.update(registry_entry.get("secondary_repositories") or [])
            allowed_repositories.discard(None)
            if claim.get("repository") not in allowed_repositories:
                errors.append(
                    f"{lane_id}: active_claim repository {claim.get('repository')} is outside registered lane scope"
                )
            if role != "reviewer" and state in {"CLAIMED","IMPLEMENTING","EVIDENCE_READY"}:
                reviewer = lane.get("reviewer") or {}
                if reviewer.get("state") == "APPROVED":
                    errors.append(f"{lane_id}: active pre-review worker cannot retain reviewer approval")
                if (lane.get("gates") or {}).get("G6_REVIEWER") == "PASS":
                    errors.append(f"{lane_id}: active pre-review worker cannot retain G6_REVIEWER=PASS")
                packet = lane.get("review_packet")
                if packet and packet.get("claim_id") != claim.get("claim_id"):
                    errors.append(f"{lane_id}: active claim cannot retain a review_packet from another claim")
            if role != "reviewer" and state == "CLAIMED":
                reviewer = lane.get("reviewer") or {}
                if reviewer.get("state") != "PENDING":
                    errors.append(f"{lane_id}: fresh CLAIMED worker must reset reviewer state to PENDING")
                if lane.get("review_packet"):
                    errors.append(f"{lane_id}: fresh CLAIMED worker must not retain a prior review_packet")
                gs = lane.get("gates") or {}
                for gate in ("G1_IMPLEMENTATION","G2_STATIC","G3_CI","G4_INTEGRATION","G6_REVIEWER","G7_CANONICAL_SYNC"):
                    if gs.get(gate) != "PENDING":
                        errors.append(f"{lane_id}: fresh CLAIMED worker must reset {gate}=PENDING")
                if lane.get("evidence"):
                    errors.append(f"{lane_id}: fresh CLAIMED worker must reset current evidence")
        if state in {"IMPLEMENTING","EVIDENCE_READY","REVIEW_REQUIRED"}:
            checkpoint = lane.get("last_checkpoint") or {}
            if not checkpoint:
                errors.append(f"{lane_id}: {state} requires last_checkpoint")
            elif claim:
                if checkpoint.get("claim_id") != claim.get("claim_id"):
                    errors.append(f"{lane_id}: last_checkpoint claim_id mismatch")
                if checkpoint.get("work_item") != claim.get("work_item"):
                    errors.append(f"{lane_id}: last_checkpoint work_item mismatch")
                if not checkpoint.get("summary"):
                    errors.append(f"{lane_id}: last_checkpoint missing summary")
                if not checkpoint.get("next_action"):
                    errors.append(f"{lane_id}: last_checkpoint missing next_action")
        if state == "REVIEW_REQUIRED":
            packet = lane.get("review_packet") or {}
            if role == "reviewer":
                errors.append(f"{lane_id}: reviewer lane must not use worker REVIEW_REQUIRED state")
            if not claim:
                errors.append(f"{lane_id}: REVIEW_REQUIRED requires active claim")
            else:
                if packet.get("claim_id") != claim.get("claim_id"):
                    errors.append(f"{lane_id}: review_packet claim_id mismatch")
                if packet.get("work_item") != claim.get("work_item"):
                    errors.append(f"{lane_id}: review_packet work_item mismatch")
                if packet.get("repository") != claim.get("repository"):
                    errors.append(f"{lane_id}: review_packet repository mismatch")
            for field in ("schema_version","submitted_at","lane_id","claim_id","work_item","repository","summary","changes","evidence","known_risks","reviewer_checks","roadmap_impact"):
                if field not in packet:
                    errors.append(f"{lane_id}: REVIEW_REQUIRED review_packet missing {field}")
            if packet.get("lane_id") != lane_id:
                errors.append(f"{lane_id}: review_packet lane_id mismatch")
            if packet.get("schema_version") != 1:
                errors.append(f"{lane_id}: review_packet schema_version must be 1")
            if not packet.get("changes"):
                errors.append(f"{lane_id}: review_packet requires changes")
            if not packet.get("evidence"):
                errors.append(f"{lane_id}: review_packet requires evidence")
            if not packet.get("reviewer_checks"):
                errors.append(f"{lane_id}: review_packet requires reviewer_checks")
            if claim:
                try:
                    control_plane_manager._validate_review_packet(lane_id, claim, packet)
                except ValueError as error:
                    errors.append(f"{lane_id}: review_packet schema invalid: {error}")
        if state == "BLOCKED" and (lane.get("block_reason") or {}).get("code") == "CANONICAL_SYNC_REQUIRED":
            if claim:
                errors.append(f"{lane_id}: CANONICAL_SYNC_REQUIRED must have no active claim")
            if (lane.get("gates") or {}).get("G7_CANONICAL_SYNC") != "PENDING_ROADMAP_SYNC":
                errors.append(f"{lane_id}: CANONICAL_SYNC_REQUIRED requires G7_CANONICAL_SYNC=PENDING_ROADMAP_SYNC")
            if not (lane.get("block_reason") or {}).get("roadmap_refs"):
                errors.append(f"{lane_id}: CANONICAL_SYNC_REQUIRED requires roadmap_refs")
        if state in {"VERIFIED","DONE"} and not lane.get("evidence"):
            errors.append(f"{lane_id}: {state} requires evidence")
        if state == "DONE":
            gs = lane.get("gates") or {}
            for gate in ("G0_CLAIM","G1_IMPLEMENTATION","G2_STATIC","G3_CI","G4_INTEGRATION","G6_REVIEWER","G7_CANONICAL_SYNC"):
                if gs.get(gate) != "PASS":
                    errors.append(f"{lane_id}: DONE requires {gate}=PASS")
    if registry_ids != seen_ids:
        errors.append(
            "chat-registry does not match canonical workstreams: "
            f"missing={sorted(seen_ids - registry_ids)} extra={sorted(registry_ids - seen_ids)}"
        )
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
