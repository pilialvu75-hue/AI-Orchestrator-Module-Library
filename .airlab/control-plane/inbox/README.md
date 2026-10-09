# Transactional control-plane inbox

Operational automations and API-driven chats must not edit canonical workstream JSON or
`canonical-state.json` directly on `main`.

Instead, create one JSON request under:

`.airlab/control-plane/inbox/pending/<request_id>.json`

The reconcile workflow applies the request to a temporary copy of the canonical state,
validates the candidate, and only then copies the resulting lane + projection into the
working tree for one commit.

Every request must contain:
- `schema_version: 1`
- a unique `request_id`
- a non-empty `actor_id`
- `lane_id`
- `operation`
- the exact `expected_state_version` read before submission
- an operation-specific `payload`

Optional `submitted_at` is retained in the receipt. `actor_id` is mandatory.

Supported ordinary operations:
- `claim`
- `heartbeat`
- `checkpoint`
- `release`
- `submit_review`
- `record_review_gates`
- `review_accept`
- `review_rework`
- `canonical_sync_complete`

### Evidence-backed reviewer gate recording

After a worker submits a claim-bound `REVIEW_REQUIRED` packet, interactive
`chatgpt:main-reviewer` may submit `record_review_gates` against the exact
worker lane `expected_state_version`. The payload requires a non-empty
`summary` and `evidence_indices` containing **exactly** G1_IMPLEMENTATION,
G2_STATIC, G3_CI and G4_INTEGRATION, each mapped to a non-empty list of
zero-based indices into the immutable review packet's `evidence` array.

Only `PASS` evidence of an appropriate type is accepted (implementation:
commit/PR; static: test/CI; CI: CI; integration: test/CI/analysis). The operation
records exact evidence refs per gate and upgrades **only** G1–G4 to PASS.
G5 physical/runtime acceptance, G6 independent review and G7 canonical sync
are never modified by this operation. Automated actors and worker chats
cannot use it. Invalid actor, missing evidence, wrong indices, or stale version
are quarantined transactionally. Passing G1–G4 does **not** approve the PR;
`review_accept` remains separate and Main/Reviewer must inspect the diff,
testing scope, risks, and actual target runtime evidence before declaring
any runtime success.

CP-HARDEN-07 extends the same serialized inbox with two wait lifecycle operations processed
before ordinary claims by `tools/control_plane_wait_inbox.py`:
- `enter_wait`
- `resume_wait`

`enter_wait` consumes a live `CLAIMED` / `IMPLEMENTING` / `EVIDENCE_READY` claim and stores
a machine-readable `wait_state` while setting the lane to `BLOCKED`. This is an equivalent
representation of `WAITING_OWNER` / `WAITING_EXTERNAL` that remains compatible with the
existing canonical status validator. The lane has `active_claim: null`, so it needs no
heartbeat and never appears in `checkpoint_watch`, but its `work_item`, branch and resource
locks remain reserved inside `wait_state`.

Required `enter_wait` payload fields:
- `wait_type`: `WAITING_OWNER` or `WAITING_EXTERNAL`
- `resume_condition`
- `summary`
- `next_action`
- optional `evidence_refs`

`resume_wait` requires an explicit non-empty `signal_id` plus non-empty `evidence_refs`.
It archives the wait record, clears the wait/block, and returns the lane to `READY` with no
new claim. Resuming therefore never silently restarts implementation; a later bounded claim
is still required.

Before the ordinary inbox processes pending `claim` requests, wait reservations are checked.
A claim is quarantined when its `work_item` or any normalized resource/branch lock overlaps a
machine-readable wait reservation. Distinct resources remain parallelizable.

For automation actors, wait operations inherit the nearest existing CP-HARDEN-04 authority
until the registry schema is versioned again: `enter_wait` requires canonical `release`
authority, while `resume_wait` requires canonical `claim` authority. Owner/target-lane rules
continue to be enforced by the automation registry.

Example ordinary claim:

```json
{
  "schema_version": 1,
  "request_id": "cantiere-20261001T180000Z-claim-001",
  "submitted_at": "2026-10-01T18:00:00Z",
  "actor_id": "chatgpt:cantiere-example",
  "lane_id": "cantiere",
  "operation": "claim",
  "expected_state_version": 12,
  "payload": {
    "work_item": "manga-physical-retest",
    "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
    "scope": "One bounded physical-retest preparation item",
    "resource_locks": [
      "resource:manga-kids-physical-acceptance",
      "contract:cantiere-lifecycle"
    ]
  }
}
```

Example wait entry:

```json
{
  "schema_version": 1,
  "request_id": "cantiere-20261003T180000Z-enter-wait-001",
  "actor_id": "chatgpt:cantiere-example",
  "lane_id": "cantiere",
  "operation": "enter_wait",
  "expected_state_version": 15,
  "payload": {
    "wait_type": "WAITING_OWNER",
    "resume_condition": "physical Manga Kids validation is completed",
    "summary": "Implementation is ready; only physical acceptance remains.",
    "next_action": "Resume after device evidence arrives.",
    "evidence_refs": ["Ai-orchestrator-riserva#745"]
  }
}
```

Accepted requests are removed from `pending/` and receive a receipt under
`processed/`. Invalid, stale, conflicting or schema-breaking requests are removed from
`pending/` and receive a receipt under `quarantine/` without changing the lane.

The compare-and-swap `expected_state_version` is mandatory. A stale writer must reread
the lane and submit a new request instead of overwriting newer work.

Claim requests may declare `payload.resource_locks` as namespaced strings such as
`file:<repo>:<path>`, `contract:<name>`, `resource:<name>`, `scope:<name>` or
`pr:<repo>#<number>`. If `payload.branch` is present, the claim manager adds the
corresponding `branch:<repo>:<branch>` lock automatically. A request is quarantined if
any requested lock is already owned by another active claim or reserved by a machine-readable
wait, even when the two work items and lanes are different. Distinct lock keys remain safe
to process in parallel.

The serialized reconcile workflow plus lane compare-and-swap protects the lane mutation;
resource locks protect shared cross-lane resources that lane-local state versions alone
cannot detect. Active locks remain held while the claim remains active, including reviewer
rework. Wait reservations preserve the same exclusion boundary without preserving a lease.

Automation identities are additionally governed by
`.airlab/control-plane/automation-registry.json`. Any `actor_id` beginning with
`automation:` must have exactly one canonical registry entry. The entry must be enabled,
hold `control_plane_mutation` write capability, allow the mapped operation and allow the
target lane. Unregistered, disabled, read-only or out-of-scope automation requests are
quarantined before compare-and-swap/application. External scheduler enablement alone never
grants control-plane write authority.

This inbox protects API-driven state changes. Repository code changes to the control-plane
implementation itself still use normal branches, pull requests and CI.
