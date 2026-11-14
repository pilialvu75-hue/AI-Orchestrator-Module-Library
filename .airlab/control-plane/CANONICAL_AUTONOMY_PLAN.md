# Canonical state autonomy — implementation contract

Status: PROPOSED. This document does not grant new mutation permissions or alter existing gates.

## Objective
Remove operational dependence on a dedicated chat for routine coordination while retaining authenticated, auditable, fail-closed promotion and runtime evidence.

## Existing infrastructure
- Hourly and event-triggered `control-plane-reconcile.yml`.
- Compare-and-swap mutation inbox, automation registry, deterministic projection.
- Claim leases, global resource locks, stale-claim reconciliation and checkpoints.

## Required implementation sequence
1. Inventory all references to `main-reviewer`, `G6_REVIEWER`, `review-accept`, `review-rework` and promotion checks in scripts, schemas, workflows, tests, lane registry and docs. Do not change a single JSON gate in isolation.
2. Define a replacement **automated verification authority** with explicit actor registration, least-privilege operation allowlists, exact-head CI and static/integration evidence, duplicate/scope checks, and immutable audit receipts.
3. Separate review-independent *coordination* transitions (claims, waits, checkpoints, projection) from *acceptance* transitions (VERIFIED/DONE). No self-approval from the same worker execution.
4. Migrate policy, schema, manager, inbox processors, workflow, validation and tests together. Preserve fail-closed behavior for unknown or stale evidence.
5. Test wrong actor, expired claim, changed head, missing CI, duplicate work, malformed receipt, replay, tampered evidence and cross-lane lock conflicts. Require successful GitHub CI before merge.
6. For evolution claim `evo-a18f2c13c19927904ced0bbd`, use historical immutable staged provenance from PR #73, not mutable queue content. No duplicate claim, no invented receipt, no consumer execution until separately authorized and verified.
7. Retain target-device validation for hardware/runtime claims and update roadmap, decisions, handoff and canonical state atomically.

## Acceptance criteria
- Routine coordination can complete without a dedicated Main/Reviewer chat.
- Independent automated verification is reproducible and cannot be bypassed by workers.
- Canonical projection is stable and idempotent; no-op runs produce no commits.
- Stale/conflicting claims remain blocked until evidence-backed reconciliation.
- Existing platform CI and physical acceptance obligations remain intact.

## Scope guard
This document is a migration specification, not an authorization to disable `G6_REVIEWER` in the current production schema. The current main policy remains authoritative until a complete tested replacement is merged.
