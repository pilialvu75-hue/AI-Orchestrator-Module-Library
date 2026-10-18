#!/usr/bin/env python3
import json
import re
import control_plane_manager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CP = ROOT / ".airlab" / "control-plane"
ALLOWED = {"READY","CLAIMED","IMPLEMENTING","EVIDENCE_READY","REVIEW_REQUIRED","VERIFIED","DONE","BLOCKED","PAUSED"}
WORKER_MAX = {"READY","CLAIMED","IMPLEMENTING","EVIDENCE_READY","REVIEW_REQUIRED","BLOCKED","PAUSED"}
AUTOMATION_OPERATIONS = {"claim","heartbeat","checkpoint","release","submit_review","record_review_gates","review_accept","review_rework","canonical_sync_complete"}
AUTOMATION_TARGET_POLICIES = {"owner_lane_only","worker_lanes_only","explicit","all_canonical_lanes","read_only","system_processor_only"}

def load(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def validate(root=ROOT):
    errors = []
    canonical = load(root / ".airlab/control-plane/canonical-state.json")
    gates = load(root / ".airlab/control-plane/gates.json")
    inference = load(root / ".airlab/control-plane/inference-policy.json")
    registry = load(root / ".airlab/control-plane/chat-registry.json")
    automation_registry = load(root / ".airlab/control-plane/automation-registry.json")
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

    if automation_registry.get("schema_version") != 1:
        errors.append("automation-registry schema_version must be 1")
    automation_policy = automation_registry.get("policy") or {}
    if automation_policy.get("mutation_actor_id_required") is not True:
        errors.append("automation-registry policy must require actor_id for mutations")
    if automation_policy.get("automation_actor_prefix") != "automation:":
        errors.append("automation-registry automation_actor_prefix must be automation:")
    for key in (
        "unregistered_automation_behavior",
        "disabled_automation_behavior",
        "missing_write_capability_behavior",
        "disallowed_operation_behavior",
        "disallowed_target_lane_behavior",
    ):
        if automation_policy.get(key) != "QUARANTINE":
            errors.append(f"automation-registry policy {key} must be QUARANTINE")

    automation_ids = set()
    automation_actor_ids = set()
    for entry in automation_registry.get("automations") or []:
        automation_id = entry.get("automation_id")
        actor_id = entry.get("actor_id")
        owner_lane = entry.get("owner_lane")
        if not isinstance(automation_id, str) or not automation_id:
            errors.append("automation-registry entry missing automation_id")
            continue
        if automation_id in automation_ids:
            errors.append(f"duplicate automation_id: {automation_id}")
        automation_ids.add(automation_id)
        if not isinstance(actor_id, str) or not actor_id:
            errors.append(f"{automation_id}: automation actor_id must be a non-empty string")
        elif actor_id in automation_actor_ids:
            errors.append(f"duplicate automation actor_id: {actor_id}")
        else:
            automation_actor_ids.add(actor_id)
        if not isinstance(entry.get("enabled"), bool):
            errors.append(f"{automation_id}: enabled must be boolean")
        if owner_lane not in registry_ids:
            errors.append(f"{automation_id}: unknown owner_lane {owner_lane}")
        if not isinstance(entry.get("scope"), str) or not entry.get("scope").strip():
            errors.append(f"{automation_id}: scope must be a non-empty string")
        for field in ("read_capabilities","write_capabilities","read_repositories","write_repositories","allowed_operations","allowed_target_lanes","forbidden_takeover_rules"):
            value = entry.get(field)
            if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
                errors.append(f"{automation_id}: {field} must be a list of non-empty strings")
        operations = entry.get("allowed_operations") or []
        invalid_operations = sorted(set(operations) - AUTOMATION_OPERATIONS)
        if invalid_operations:
            errors.append(f"{automation_id}: invalid allowed_operations {invalid_operations}")
        target_policy = entry.get("target_lane_policy")
        if target_policy not in AUTOMATION_TARGET_POLICIES:
            errors.append(f"{automation_id}: invalid target_lane_policy {target_policy}")
        allowed_targets = entry.get("allowed_target_lanes") or []
        unknown_targets = sorted(set(allowed_targets) - registry_ids)
        if unknown_targets:
            errors.append(f"{automation_id}: unknown allowed_target_lanes {unknown_targets}")
        write_capabilities = entry.get("write_capabilities") or []
        mutating = "control_plane_mutation" in write_capabilities
        if mutating:
            if not isinstance(actor_id, str) or not actor_id.startswith("automation:"):
                errors.append(f"{automation_id}: mutating automation actor_id must start with automation:")
            if not operations:
                errors.append(f"{automation_id}: mutating automation requires allowed_operations")
            if target_policy not in {"owner_lane_only","worker_lanes_only","explicit","all_canonical_lanes"}:
                errors.append(f"{automation_id}: mutating automation requires a writable target_lane_policy")
            if "pilialvu75-hue/AI-Orchestrator-Module-Library" not in (entry.get("write_repositories") or []):
                errors.append(f"{automation_id}: control-plane mutation requires Module Library write scope")
        elif operations:
            errors.append(f"{automation_id}: non-mutating automation cannot declare allowed_operations")
        if entry.get("kind") == "reviewer":
            if target_policy != "worker_lanes_only":
                errors.append(f"{automation_id}: reviewer automation must target worker_lanes_only")
            if "OWNER_LANE_TAKEOVER_FORBIDDEN" not in (entry.get("forbidden_takeover_rules") or []):
                errors.append(f"{automation_id}: reviewer automation must forbid owner lane takeover")
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
    active_resource_locks = {}
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
        pending_delivery = lane.get("pending_needs_delivery")
        if pending_delivery is not None:
            claim_pending = lane.get("active_claim")
            packet_pending = lane.get("review_packet")
            identity_pending = (pending_delivery.get("identity")
                                if isinstance(pending_delivery, dict) else None)
            gates_pending = lane.get("gates") or {}
            reviewer_pending = lane.get("reviewer") or {}
            if (lane_id != "library-curation" or state != "REVIEW_REQUIRED"
                    or not isinstance(claim_pending, dict)
                    or not isinstance(packet_pending, dict)
                    or not isinstance(identity_pending, dict)
                    or pending_delivery.get("profile") != "library-needs-only-v1"
                    or pending_delivery.get("changed_file") != "catalog/needs.json"):
                errors.append(f"{lane_id}: invalid prepared needs-only delivery state")
            else:
                if (identity_pending.get("lane_id") != lane_id
                        or identity_pending.get("claim_id") != claim_pending.get("claim_id")
                        or identity_pending.get("packet_sha256") != control_plane_manager._review_packet_digest(packet_pending)
                        or identity_pending.get("repository") != claim_pending.get("repository")
                        or identity_pending.get("pr_number") != packet_pending.get("pull_request")
                        or type(identity_pending.get("state_version")) is not int
                        or identity_pending["state_version"] + 1 != lane.get("state_version")):
                    errors.append(f"{lane_id}: prepared needs-only identity mismatch")
                for sha_key in ("head_sha",):
                    sha = identity_pending.get(sha_key)
                    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                        errors.append(f"{lane_id}: prepared needs-only {sha_key} invalid")
                scope_sha = pending_delivery.get("scope_blob_sha")
                if not isinstance(scope_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", scope_sha):
                    errors.append(f"{lane_id}: prepared needs-only blob SHA invalid")
                if (gates_pending.get("G6_REVIEWER") != "PENDING"
                        or gates_pending.get("G7_CANONICAL_SYNC") != "PENDING"
                        or gates_pending.get("G5_TARGET_RUNTIME") not in (
                            "NOT_APPLICABLE", "NOT_APPLICABLE_UNTIL_RUNTIME_CHANGE"
                        )
                        or reviewer_pending.get("state") != "PENDING"):
                    errors.append(f"{lane_id}: prepared delivery cannot bypass G5/G6/G7")
                for gate in ("G1_IMPLEMENTATION", "G2_STATIC", "G3_CI", "G4_INTEGRATION"):
                    if gates_pending.get(gate) != "PASS":
                        errors.append(f"{lane_id}: prepared needs-only delivery requires {gate}=PASS")
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

            resource_locks = claim.get("resource_locks") or []
            try:
                normalized_locks = control_plane_manager._normalize_resource_locks(
                    resource_locks,
                    repository=str(claim.get("repository") or ""),
                    branch=None,
                )
            except ValueError as error:
                errors.append(f"{lane_id}: active_claim resource_locks invalid: {error}")
                normalized_locks = []
            else:
                if resource_locks != normalized_locks:
                    errors.append(
                        f"{lane_id}: active_claim resource_locks must be sorted unique canonical keys"
                    )
                branch = claim.get("branch")
                if branch is not None:
                    if not isinstance(branch, str) or not branch.strip():
                        errors.append(f"{lane_id}: active_claim branch must be a non-empty string or null")
                    else:
                        branch_lock = f"branch:{claim.get('repository')}:{branch.strip()}"
                        if branch_lock not in normalized_locks:
                            errors.append(f"{lane_id}: active_claim missing derived branch lock {branch_lock}")
                for lock_key in normalized_locks:
                    owner = active_resource_locks.get(lock_key)
                    if owner:
                        errors.append(
                            f"duplicate active resource lock {lock_key}: {owner} and {lane_id}"
                        )
                    else:
                        active_resource_locks[lock_key] = lane_id

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
