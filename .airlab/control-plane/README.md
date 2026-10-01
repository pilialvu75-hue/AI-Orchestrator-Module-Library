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

Claims are leases in meaning even before lease automation exists. A stale claim must be reconciled, never silently ignored.

## One engine, many bodies

Platform lanes exist to make the same product work on different targets.
They may adapt:
- packaging/install/update;
- OS APIs and permissions;
- hardware acceleration adapters;
- audio/video device integration;
- filesystem/process/window integration;
- UI shell/layout where target conventions require it.

They must not independently fork shared inference, routing, memory, voice-core, Diagnostics contracts or Cantiere lifecycle.
A needed shared change is proposed to the relevant shared lane and reviewed for all affected platforms.

## Gate ladder

`READY -> CLAIMED -> IMPLEMENTING -> EVIDENCE_READY -> REVIEW_REQUIRED -> VERIFIED -> DONE`

`BLOCKED` and `PAUSED` are explicit non-success states.

CI green is G3, not DONE.
Runtime/hardware claims require G5 target evidence.
