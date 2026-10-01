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
- `lane_id`
- `operation`
- the exact `expected_state_version` read before submission
- an operation-specific `payload`

Optional `submitted_at` and `actor_id` fields are retained in the receipt.

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
  "actor_id": "automation:cantiere",
  "lane_id": "cantiere",
  "operation": "claim",
  "expected_state_version": 12,
  "payload": {
    "work_item": "manga-physical-retest",
    "repository": "pilialvu75-hue/Ai-orchestrator-riserva",
    "scope": "One bounded physical-retest preparation item"
  }
}
```

Accepted requests are removed from `pending/` and receive a receipt under
`processed/`. Invalid, stale, conflicting or schema-breaking requests are removed from
`pending/` and receive a receipt under `quarantine/` without changing the lane.

The compare-and-swap `expected_state_version` is mandatory. A stale writer must reread
the lane and submit a new request instead of overwriting newer work.

This inbox protects API-driven state changes. Repository code changes to the control-plane
implementation itself still use normal branches, pull requests and CI.
