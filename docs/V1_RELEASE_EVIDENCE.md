# Module Library V1.0.0 — Release Evidence

This document freezes the evidence for the deterministic Module Library V1 engine. It does **not** claim that the production catalog is already fully populated.

## Core Library

V1 includes:

- authoritative needs/catalog/contracts and strict schemas;
- discovered -> quarantined -> normalized -> tested -> certified lifecycle;
- immutable certified versions and append-only observations;
- deprecation/revocation/reinstatement + rollback planning;
- deterministic resolver and integrity-protected offline snapshot;
- verified Cantiere intake bundle materialization;
- certified package export for Cantiere;
- event-driven, fail-closed certification autopilot;
- local test/security evidence verification before a candidate can reach `tested` or `certified`.

## Cross-repository boundaries already merged

### Cantiere / app

The current `Ai-orchestrator-riserva` main contains the V1 path for:

- project capability shopping list;
- reuse-first planning;
- safe assembly/adaptation;
- verified-output capture and persisted reuse learning;
- immutable intake payload bundle;
- GitHub Device Flow authentication and private-Library PR submission;
- Library snapshot/package verification and consumption;
- Modules dashboard with Library-authoritative counts.

Representative merged PRs: #327, #328, #329, #339, #340, #341, #342, #343, #344, #345, #346, #349, #350.

### Researcher

The independent Researcher V1 contains:

- capability progress/status;
- immutable-license normalizable intake;
- restart-safe/idempotent submission;
- shared Diagnostics producer;
- controlled research proofs and pinned-candidate admission.

A real Researcher candidate (`storage.local_db.simolus3.drift@0.1.0`) has crossed the actual GitHub boundary into this Library.

## Real fail-closed production smoke

The Drift candidate currently states:

- `status = discovered`;
- `validation.tests_passed = false`;
- `security.reviewed = false`.

After merge, the real `Certify eligible intake` workflow processed it and returned a blocked result instead of promoting it. The blocking reason was that a tested asset requires `validation.tests_passed=true`.

This is expected and is release evidence: the Library does not turn Researcher confidence into certification.

## Certification evidence contract

A successful certification claim must now be backed by files inside the immutable candidate tree.

When `validation.tests_passed=true`:

- `validation.test_report` must exist inside the asset directory;
- it must use `ai-orchestrator.library-test-report.v1`;
- asset id/version/source commit must match the manifest;
- the report must assert `passed=true`;
- report targets must match `validation.validated_on` and must be declared asset platforms.

When `security.reviewed=true`:

- `security.review_report` must exist inside the asset directory;
- it must use `ai-orchestrator.library-security-review.v1`;
- asset id/version/source commit must match the manifest;
- vulnerability count must match the manifest;
- `security.sbom` must exist locally;
- the security review must bind the exact SBOM using SHA-256.

Existing license, provenance, vulnerability-count and copyleft gates remain in force.

## Release acceptance

V1.0.0 is accepted when the V1 evidence-hardening PR is fully green and merged to `main`.

Catalog coverage remains operational work after release. A candidate is not promoted merely to satisfy a release milestone.
