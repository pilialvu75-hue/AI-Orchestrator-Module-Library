# LIB-2 — Capture / Promotion Pipeline

Status: implementation complete on `library-promotion-v1`; merge pending final CI/PR validation.

Completion criteria:

- intake is the only pre-certification write entry point;
- lifecycle transitions cannot be skipped by the pipeline;
- normalization checks provenance, payload and Lego connector metadata;
- tested state requires passing tests, score >= 0.80, timestamp and tested targets;
- certification re-checks all gates plus security review and license policy;
- automatic certification blocks candidates with known vulnerabilities;
- automatic certification blocks strong/network-copyleft cases pending explicit project-level review;
- immutable `(asset-id, version)` destinations are never overwritten;
- dry-run performs preflight without repository mutation;
- successful promotion creates the certified module and one catalog entry, bumps catalog version and removes the intake copy only after successful writes;
- repeated completed promotion is idempotent;
- repository validator and promotion unit/integration tests run in CI;
- end-to-end test proves a tested intake fixture can be promoted and then accepted by the main Library validator.

Next roadmap step after merge: versioning/evolution, historical quality/compatibility and deprecation/revocation mechanics.
