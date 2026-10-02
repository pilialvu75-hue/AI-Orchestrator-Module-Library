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

Supported operations:
- `claim`
- `heartbeat`
- `checkpoint`
- `release`
- `submit_review`
- `review_accept`
- `review_rework`
- `canonical_sync_complete`

Example:

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

Accepted requests are removed from `pending/` and receive a receipt under
`processed/`. Invalid, stale, conflicting or schema-breaking requests are removed from
`pending/` and receive a receipt under `quarantine/` without changing the lane.

The compare-and-swap `expected_state_version` is mandatory. A stale writer must reread
the lane and submit a new request instead of overwriting newer work.

Claim requests may declare `payload.resource_locks` as namespaced strings such as
`file:<repo>:<path>`, `contract:<name>`, `resource:<name>`, `scope:<name>` or
`pr:<repo>#<number>`. If `payload.branch` is present, the claim manager adds the
corresponding `branch:<repo>:<branch>` lock automatically. A request is quarantined if
any requested lock is already owned by another active claim, even when the two work items
and lanes are different. Distinct lock keys remain safe to process in parallel.

The serialized reconcile workflow plus lane compare-and-swap protects the lane mutation;
resource locks protect shared cross-lane resources that lane-local state versions alone
cannot detect. Locks remain held while the claim remains active, including reviewer rework.

Automation identities are additionally governed by
`.airlab/control-plane/automation-registry.json`. Any `actor_id` beginning with
`automation:` must have exactly one canonical registry entry. The entry must be enabled,
hold `control_plane_mutation` write capability, allow the requested operation and allow the
target lane. Unregistered, disabled, read-only or out-of-scope automation requests are
quarantined before compare-and-swap/application. External scheduler enablement alone never
grants control-plane write authority.

This inbox protects API-driven state changes. Repository code changes to the control-plane
implementation itself still use normal branches, pull requests and CI.
