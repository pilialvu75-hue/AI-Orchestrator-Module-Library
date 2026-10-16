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
