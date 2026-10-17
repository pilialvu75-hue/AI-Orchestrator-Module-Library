# Autonomous completion: trusted verifier contract (not active)

The worker and its review packet are untrusted inputs. A worker-controlled lane JSON
field, including `verified_by` or `trusted_verifier_receipt`, is never authority.

## Independent verifier

Run in a protected GitHub Actions workflow on the canonical default branch.
Do not execute code from the worker pull request with write credentials.
Fetch PR metadata and check runs using GitHub's API; require the exact head SHA,
repository, workflow identity, successful conclusion, and a completed run.
A self-reported CI evidence entry is insufficient. Reject missing, stale,
cancelled, skipped, or mismatched checks.

Bind the verified evidence to lane ID, state_version, claim ID, packet digest,
repository, PR number and head SHA. Record a trusted result through the
protected reconciliation process, not through a worker-editable field.
Use an idempotent request ID and enforce expected_state_version.

## Protected receipt handoff (required before activation)

The read-only CI probe output is **not** a trusted completion receipt. The
protected verifier must additionally obtain the canonical lane snapshot and
bind `lane_id`, exact `state_version`, live `claim_id`, and canonical
`packet_sha256` to the GitHub API-verified `repository`, `pr_number`, and
`head_sha`. The verifier must check the required gates and target-runtime
applicability against trusted evidence rather than worker-authored PASS flags.

The handoff must have a protected provenance channel (for example, a
restricted default-branch workflow artifact identified by run ID and verified
through the GitHub API), with an explicit allowlist of workflow identity,
repository, branch, conclusion, and run attempt. A worker-provided receipt
URL, JSON boolean, actor label, or run ID alone must never authorize mutation.
The inbox consumer must independently re-fetch the protected receipt and
revalidate its bindings at the time of transaction, including unchanged PR
head and unchanged canonical state version. A successful preflight without
this protected handoff remains read-only and fails closed.

## Receipt artifact verification requirements

The protected workflow must produce a dedicated receipt artifact containing the
canonical identity and API-verified PR/check evidence. The inbox consumer must
retrieve the artifact through GitHub's API for the allowlisted workflow run,
rather than accepting a worker-provided receipt body or URL. Verify the artifact
belongs to the exact run ID and attempt, and reject expired, missing, ambiguous,
or multiple matching artifacts. Treat an artifact name as a selector, not proof.

The consumer must parse the receipt with a strict schema and size limit, compare
all identity fields to a freshly loaded canonical lane snapshot, and independently
re-fetch the PR head and required checks. The protected run's success alone does
not prove that a receipt artifact was created, that its contents were validated,
or that the canonical lane remains unchanged.

Before any mutation, check the canonical state version again under the inbox
transaction lock. A duplicate request must remain a no-op, and any missing
receipt provenance, stale claim, changed PR head, or unresolved runtime gate
must fail closed. No worker-supplied flag or local mock may set
`completion_authorized` to true.

## Canonical CI binding on PR #120 (read-only, not activated)

The `autonomous-ci-probe.yml` workflow now requires `lane_id` and checks out
the exact `github.sha` associated with its protected `workflow_dispatch` run,
rather than following a potentially moving `main` reference. The canonical
producer `tools/autonomous_canonical_ci_probe.py` reads the protected
`.airlab/control-plane/canonical-state.json` workstream registry and matching
worker lane, verifies that the claim lease is live, and derives the complete
seven-field identity from the canonical claim/packet plus GitHub API PR data.
The live CI probe must independently confirm the same PR head.

The protected artifact must now contain `canonical_identity`; the consumer
rejects missing, altered, or stale identities and re-fetches the required check
runs from GitHub. Every output still carries
`trusted_receipt=false` and `completion_authorized=false`.

These changes are staged on PR #120. Passing its unit/CI checks does not
demonstrate that the modified protected workflow has run on default-branch
`main`; it can only be exercised there after merge. Remaining activation
requirements include independent G1/G2/G4 and G5 evidence authentication,
a dedicated completion-authority receipt, the inbox compare-and-swap mutation,
and a coherent replacement for the historical G6 reviewer rule. Never treat
`canonical_identity` or this artifact alone as approval.

## State transition

Only after trusted verification may a dedicated transaction release a live
claim and move the lane to READY, or BLOCKED when material roadmap sync remains.
Never fabricate G6_REVIEWER=PASS or reviewer history. Update the validator and
gate schema together with the transaction, and preserve G5 physical/runtime
requirements. Fail closed on any missing provenance.

## Activation criteria

1. Trusted verifier workflow and its permissions are reviewed.
2. Negative tests cover forged receipts, wrong SHA, wrong lane, expired claims,
   missing required CI, duplicate requests, and runtime evidence gaps.
3. The transactional inbox operation and canonical validator agree.
4. CI passes on the exact PR head and the change is merged to the default branch.
5. Only then enable the worker automation in the canonical registry.

Current state: **NOT ACTIVE**. This document is an implementation contract,
not a claim that the Library can already complete work autonomously.
