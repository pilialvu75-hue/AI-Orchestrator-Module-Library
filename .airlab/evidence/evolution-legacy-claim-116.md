# Evolution claim #116 — historical provenance and proposed reconciliation

**Status:** REVIEW_REQUIRED — proposal only; no queue mutation authorized.

- Work ID: `evo-a18f2c13c19927904ced0bbd`
- Capability: `ai.acceleration_backend`
- Original staged commit: `9a3525854e0319664b5974590065941efefa7f5b` (PR #73)
- Original staged blob: `3530258ca51449dbf62e3bd38427206b282829e7`
- Claimed transition: `ab5b88e602a2f9f89983e28c4ca50aa33ce50d3a` (PR #75)
- Observed transition patch: `state: staged -> claimed` only.
- Direct structured comparison against current main, excluding `state`: identical (observed 2026-10-15).
- Source of immutable provenance: Git historical commit/blob, **not** mutable current queue content.

## Reviewer gate

1. Independently verify the Git commits, blob, and transition patch.
2. Reconstruct the envelope from the original staged blob using the current `_claim_envelope` contract. Verify the exact schema, work ID, proposal ID, capability, objective, knowledge delta, gates, mutation policy, output, and source.
3. Compute SHA-256 over canonical JSON (sorted keys, compact separators, UTF-8). Review the resulting digest and approve or reject a **separate** narrowly scoped migration of the queue record.
4. Migration must fail closed if current queue content diverges from the immutable staged record or state is no longer `claimed`; preserve state and do not create a second claim.
5. Validate the migration with tampering, idempotency, wrong-state, and historical-evidence regression tests on the exact PR head.
6. Only after reviewer approval and passing CI may the isolated consumer be invoked. Intake, security gates, receipt, and canonical state synchronization remain separate acceptance requirements.

## Explicit non-claims

This record does not assert that a digest was stored at the time of the historical claim, that the original consumer ran, that a Library intake was produced, or that the target runtime was validated. Do not mark the work `returned` or `DONE` based on this evidence alone.

Related: issue #116, merged PR #110, Riserva PR #825.
