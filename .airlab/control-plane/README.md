# Canonical Control Plane v1

This directory is the private coordination authority for parallel ChatGPT/agent work across AI Orchestrator.

## Mandatory read order

Every main/reviewer or worker chat must read, in this order:

1. `.airlab/control-plane/canonical-state.json`
2. `.airlab/control-plane/gates.json`
3. its own file under `.airlab/control-plane/workstreams/`
4. the relevant private roadmap under `.airlab/roadmap.yaml` or `.airlab/public-repositories/<repo>/roadmap.yaml`
5. repository CI, open PRs/issues and Diagnostics evidence relevant to the claimed item.

A chat must not reconstruct project state from conversational memory when canonical data is available.

## Roles

### Main reviewer
The main/reviewer lane is the only lane allowed to promote work to `VERIFIED` or `DONE`.
It checks existing work, strengthens weak fixes, detects scope drift/duplication, validates evidence, and keeps roadmap plus canonical state synchronized.

### Worker lanes
Worker chats are specialized execution lanes. They may claim work, implement, test and collect evidence.
Their maximum self-declared state is `REVIEW_REQUIRED`.

## Continuous roadmap and state

"Continuous" means event-driven, not a periodic rewrite:
- accepted evidence changes the affected workstream immediately;
- material scope/priority/dependency changes update the roadmap in the same PR;
- reviewer promotion updates canonical state in the same PR;
- a completed implementation with stale roadmap/state is not DONE.

## Claim/lock protocol

Before work:
1. inspect all active claims;
2. declare one bounded `work_item`;
3. record repository, issue/PR/branch when known;
4. do not start overlapping implementation if another active lane owns the same work item.

Claims are real leases with heartbeat. Default lease: 12 hours; maximum: 24 hours. A stale claim is never silently freed: reconciliation clears the lease, marks the lane `BLOCKED`, records the expiry event and requires reviewer reconciliation before new work.

Canonical commands:

```bash
python tools/control_plane_manager.py claim --lane cantiere --work-item issue-123 --repository pilialvu75-hue/Ai-orchestrator-riserva --scope "bounded task"
python tools/control_plane_manager.py heartbeat --lane cantiere
python tools/control_plane_manager.py release --lane cantiere --reason "superseded"
python tools/control_plane_manager.py project
python tools/control_plane_manager.py reconcile
```

The scheduled/event-driven reconciliation workflow projects merged lane state into `canonical-state.json` and only commits when the deterministic source digest changes.

## One engine, many bodies

Platform lanes exist to make the same product work on different targets.
They may adapt:
- packaging/install/update;
- OS APIs and permissions;
- hardware acceleration adapters;
- audio/video device integration;
- filesystem/process/window integration;
- UI shell/layout where target conventions require it.

They must not fork shared orchestration semantics, inference contracts, routing contracts, memory, voice-core contracts, Diagnostics contracts or Cantiere lifecycle.

Inference is the deliberate exception at the implementation/profile layer: each platform may use different LLM families, sizes, quantizations, backends and acceleration settings when target benchmarks justify them. The shared Runtime Core owns the inference contract and routing semantics; each platform lane owns its target inference profile.

A needed shared-contract change is proposed to the relevant shared lane and reviewed for all affected platforms.

## Gate ladder

`READY -> CLAIMED -> IMPLEMENTING -> EVIDENCE_READY -> REVIEW_REQUIRED -> VERIFIED -> DONE`

`BLOCKED` and `PAUSED` are explicit non-success states.

CI green is G3, not DONE.
Runtime/hardware claims require G5 target evidence.


## Target-specific inference profiles

The product is shared; the local inference implementation is not required to be identical.

Each platform lane maintains a benchmark-gated target profile covering hardware/software fingerprint, candidate models, role assignments, backend/accelerator settings, resource limits and fallbacks. See `.airlab/control-plane/inference-policy.json`.

The selection objective is balance: use the strongest practical model/profile for the target without creating memory, thermal, latency or stability problems, while avoiding an unnecessarily small model on hardware that can reliably run more capable options.

No platform profile may be promoted from benchmark results alone when installation, launch or runtime behavior also changed: G5 target-runtime evidence remains mandatory.


## Chat lane bootstrap

Every operational chat has one canonical lane registered in `.airlab/control-plane/chat-registry.json`.

Generate a current bootstrap relay from repository state instead of maintaining hand-written prompts:

```bash
python tools/chat_lane_bootstrap.py --lane main-reviewer
python tools/chat_lane_bootstrap.py --lane cantiere
python tools/chat_lane_bootstrap.py --lane voice-live
python tools/chat_lane_bootstrap.py --lane platform-windows
```

The generated relay embeds the lane identity, repository, current state, scope and mandatory operating rules. It always instructs the chat to re-read canonical repository state before work, so an old copied relay cannot override newer state.

Worker completion is a structured handoff, not a prose "done". Build a packet conforming to `.airlab/control-plane/schemas/review-packet.schema.json`, then transition the lane:

```bash
python tools/control_plane_manager.py submit-review --lane voice-live --packet /path/to/review-packet.json
```

The claim remains active while Main/Reviewer inspects the packet. Main/Reviewer then promotes, requests rework or explicitly releases/reconciles the claim.


## Full chat rollover and deletion

A chat is an execution surface, not project storage.

When a chat becomes full:
1. keep the same canonical lane id;
2. generate a fresh relay with `python tools/chat_lane_bootstrap.py --lane <lane-id>`;
3. open a new chat and paste/use that current relay;
4. the new chat reads canonical state, roadmap, workstream, claims, PR/CI and Diagnostics before continuing;
5. do not reconstruct state from the old chat unless a specific unmigrated fact is discovered.

The old chat may be deleted only after the archive gate in `canonical-state.json#chat_archive_policy` passes:
- unique actionable work migrated;
- unresolved work linked to roadmap/workstream;
- reusable evidence/decisions preserved;
- a replacement lane/bootstrap exists when work is ongoing.

The private inventory of consolidated historical chats lives at
`.airlab/control-plane/historical-chat-consolidation.json`.


## Continuous chat checkpoints

Do **not** wait for a chat to report that it is nearly full.

Operational continuity is event-driven. While a lane holds a claim, persist a checkpoint whenever material project state changes:

```bash
python tools/chat_checkpoint.py \
  --lane cantiere \
  --summary "Implemented bounded reviewer fix and CI is green." \
  --next-action "Run physical generated-app acceptance." \
  --decision "Keep Phase 1 ONLINE until physical acceptance." \
  --evidence-ref "PR #123"
```

A checkpoint:
- stores the safe resume point, decisions, evidence refs and next action in the lane;
- advances a freshly claimed lane to `IMPLEMENTING`;
- refreshes the active claim heartbeat/lease;
- updates the canonical projection.

Checkpoints are required after meaningful milestones, new blockers/diagnoses, material PR/CI/Diagnostics/runtime results, roadmap changes, and before long/high-risk work.

`submit-review` automatically records a final `REVIEW_HANDOFF` checkpoint.

The ChatGPT product does not need to expose a reliable "context almost full" signal for continuity. If a chat fills unexpectedly, the replacement chat reads the same lane and resumes from `last_checkpoint`.


## Checkpoint freshness watchdog

Hourly/event reconciliation also evaluates active claims for checkpoint freshness.

After 120 minutes without a checkpoint for the current claim, the lane appears in
`canonical-state.json#projection.checkpoint_watch` as either:
- `NO_CHECKPOINT_YET`
- `CHECKPOINT_STALE`

This is a reviewer-attention signal only. It does **not** fabricate missing chat content and
does not block a lane before the normal claim lease expires. Main/Reviewer can then inspect the
lane, current PR/CI/Diagnostics state and decide whether a real checkpoint, wait-state note,
rework or reconciliation is needed.


## Reviewer inbox and decisions

Reviewer intake is derived from the raw worker workstream files, not from
`canonical-state.json#projection.review_required` alone.

The projection is a convenience index and may temporarily lag or fail to update if a worker
handoff is invalid. Main/Reviewer must therefore use:

```bash
python tools/control_plane_manager.py review-inbox
python tools/control_plane_manager.py review-accept \
  --lane cantiere \
  --summary "Bounded implementation accepted." \
  --next-action "Run target acceptance." \
  --evidence-ref "PR #123"

python tools/control_plane_manager.py review-rework \
  --lane cantiere \
  --reason "Regression coverage incomplete." \
  --next-action "Add the missing regression test."
```

`review-inbox` scans the raw lane files and validates each review packet against its active
claim. A stale projection must never hide a valid `REVIEW_REQUIRED` lane.

Workers must never set `REVIEW_REQUIRED` by changing only the status field. A valid handoff is
atomic: active claim + valid review packet + claim-bound review checkpoint + REVIEW_REQUIRED.


## Lifecycle gap safeguards

Additional invariants close failure modes found after the first autonomous pilot:

- a claim may target only repositories registered for its lane in `chat-registry.json`;
- heartbeat, checkpoint, submit-review and voluntary release cannot revive or bypass an expired lease;
- a valid `REVIEW_REQUIRED` handoff stays reviewer-owned even when its worker lease time passes; reconciliation records `REVIEW_WAIT_OVERDUE` instead of destroying the handoff;
- material roadmap impact makes the lane `BLOCKED` with `CANONICAL_SYNC_REQUIRED` after review acceptance, so no new claim can start until the referenced roadmap state is actually synchronized;
- `canonical-sync-complete` requires the expected roadmap refs before returning the lane to `READY`;
- direct JSON edits are still validated against registered repository scope and pre-review approval invariants.

These rules complement, rather than replace, the remaining structural backlog for resource-level locks,
unclaimed external-change ingress detection, automation registration, and the AIR-10 dispatcher.


## Transactional mutation guard

API-driven operational state changes use the transactional inbox documented at
`.airlab/control-plane/inbox/README.md`.

A request is compare-and-swap guarded by the lane's `expected_state_version`. The workflow
applies it to an isolated temporary copy, validates the resulting lane/control plane, and
only then commits the accepted state. Invalid or stale requests are quarantined with a
receipt and cannot partially mutate a workstream.

Projection/reconciliation also isolates unreadable lane files. A malformed lane is surfaced
through `canonical-state.json#projection.projection_incidents`; healthy lanes remain visible.
Full validation still fails closed until the malformed lane is repaired.

Operational automations must not write workstream/canonical JSON directly to `main`.
