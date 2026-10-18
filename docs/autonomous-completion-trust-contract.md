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

## Independent Library CI gate audit (PR #120, inactive)

The protected `workflow_dispatch` probe now has explicit read-only
`actions: read` permission and pins the **Library** job check to
`validate`; the caller cannot choose a weaker check. The workflow emits an
`independent_gate_audit` alongside `canonical_identity`.

`tools/autonomous_independent_gates.py` independently queries GitHub for:

- The exact PR-head `validate-library.yml` blob, which must match the
  protected default-branch checkout (any changed PR-side workflow is refused).
- Successful `pull_request` workflow runs for that head and the exact
  `validate` check-run URL.
- Every required successful job step: control-plane, library contracts,
  history, lifecycle, unit tests, offline export, and snapshot validation.
  Skipped, missing, duplicate, failed or ambiguous job evidence is refused.

The consumer re-runs the same audit from its protected checkout and compares
the resulting report byte-for-byte at the JSON-value level with the artifact.
An audit mismatch fails closed. A full green CI proves only the checks it ran,
not that a generated module is correct at runtime or independently reviewed.

| Gate | Read-only audit status |
| --- | --- |
| G0 claim | Canonical claim and lease checked by producer |
| G1 implementation | **Pending independent implementation review** |
| G2 static | Verified CI pipeline steps, not unrestricted code approval |
| G3 CI | Exact-head successful validation check |
| G4 integration | CI contract checks observed; **independent integration review pending** |
| G5 runtime | **Applicability and target evidence unresolved** |
| G6 / completion | **Never automatically approved** |

This first gate audit is intentionally limited to
`pilialvu75-hue/AI-Orchestrator-Module-Library`. The other worker repos have
different workflows and must obtain separate allowlisted gate profiles.
The audit uses the protected checkout's trusted workflow as an input; it must
only be executed from a verified protected default-branch context. Adding
`independent_gate_audit` does not change the existing autonomous-completion
fail-closed policy, transactional inbox operation, or canonical G6 state rules.

## First real autonomous lane profile: needs queue only (PR #120)

A strictly limited production route is implemented for the
`library-curation` lane and **only a one-file change to
`catalog/needs.json`**. This is metadata queue maintenance, NOT automatic
certification or promotion of executable modules.

The independent scope verifier (`tools/autonomous_needs_scope.py`) re-fetches
GitHub's PR metadata, complete one-file diff and exact-head blob identity. It
rejects forks, drafts, non-main targets, extra files, renamed/added/deleted
files, stale heads and executable changes. The protected CI audit must verify
the unchanged protected `validate-library.yml` and all required green steps,
including catalog contracts, lifecycle and deterministic offline export. The
runtime gate must already be explicitly N/A and no runtime/physical evidence
claim is accepted. Material roadmap changes are excluded from this fast path.

An eligible worker submits a normal claim-bound `review_packet` in the
canonical inbox. The protected reconcile workflow, after serializing that
handoff onto main, dispatches the **read-only** verifier on main. Successful
protected runs trigger `workflow_run`; the reconciler independently fetches
the run, artifact, canonical identity, exact-head PR and verified scope,
then enqueues a request with ONLY `protected_run_id`, `run_attempt` and
`protected_sha`. The ordinary inbox **rechecks all evidence again** under
the current `expected_state_version` before applying it on an isolated
canonical tree and running the regular validator. A worker-supplied approval
flag never grants rights.

Successful needs-only completion records `autonomous_completion_history`,
claim/payload digest/CI run and an independent gate attestation; it releases
the claim and moves the lane to **READY**. It deliberately leaves
`G6_REVIEWER=PENDING`, does NOT write `review_history.APPROVED`,
and does NOT claim a generic `DONE` state. A subsequent claim resets
the implementation gates normally. Other software, module certification,
runtime or physical work remains on the stronger independent-verifier route.

The protected reconcile workflow uses `actions:write` only to dispatch
the allowlisted read-only verifier; `contents:write` is used only by its
existing serialized canonical state processor. PR code is never executed with
those write credentials. Dispatch is event-triggered for a changed canonical
lane; it is not a continuous polling/paid-service loop.

**Activation prerequisite:** PR #120 is merged into main, but a real eligible handoff has not yet produced an APPLIED receipt. Real confirmation requires (1) merge exact green head,
(2) a separate eligible one-file needs-only PR with live claim/packet,
(3) completed protected workflow and artifact, (4) an `APPLIED` inbox
receipt and canonical lane READY. The end-to-end tests mock authenticated
GitHub API responses and cannot substitute for that real proof.

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

Current state: **NEEDS-ONLY FAST PATH IN MAIN, REAL ACCEPTANCE PENDING**.
Generic executable-module completion and G6 replacement remain unavailable.

## Dedicated Library curation lane

The needs-only first route now exclusively targets `library-curation`, registered as an independent worker in the canonical chat and workstream registries. The existing `library-researcher` lane and Researcher claim are intentionally unchanged. A Researcher repair can therefore remain in REVIEW_REQUIRED without preventing a new, distinct Library-owned metadata task from being claimed. Independent curation does not itself provide a scheduler to author needs changes or grant module certification rights.
