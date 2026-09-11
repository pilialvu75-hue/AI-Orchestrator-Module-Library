# Promotion Pipeline

This document describes the authoritative path from an untrusted Library submission to a certified reusable asset.

## Topology

`Researcher -> intake/ <- Cantiere`

`intake/ -> gated lifecycle -> modules/ + catalog/index.json`

The Researcher and Cantiere never write directly to `modules/` or the certified catalog.

## Submission

A submission is an immutable directory:

```text
intake/<asset-id>/<semver>/
```

The directory contains `manifest.json` plus any payload, tests, provenance and license evidence required by the manifest.

Presence under `intake/` is the repository-level `submitted` event. The manifest lifecycle begins at `discovered`.

## Lifecycle

The only normal forward path is:

```text
discovered -> quarantined -> normalized -> tested -> certified
```

States cannot be skipped by `tools/library_pipeline.py`.

### Quarantined

The candidate is acknowledged but remains untrusted. No automatic reuse is permitted.

### Normalized

The candidate has coherent capability metadata, immutable external provenance where applicable, license evidence, payload references and an `ai-orchestrator-lego` connector.

### Tested

The candidate has reproducible validation evidence, `tests_passed=true`, score >= 0.80, validation timestamp and at least one tested target.

### Certified

Certification is only created by promotion. Automatic certification additionally requires a completed security review, zero recorded known vulnerabilities and no license class that requires an explicit project-level decision.

## Commands

Advance exactly one lifecycle state:

```bash
python tools/library_pipeline.py advance <asset-id> <version> quarantined
python tools/library_pipeline.py advance <asset-id> <version> normalized
python tools/library_pipeline.py advance <asset-id> <version> tested
```

Preflight a promotion without mutation:

```bash
python tools/library_pipeline.py promote <asset-id> <version> --dry-run
```

Promote:

```bash
python tools/library_pipeline.py promote <asset-id> <version>
```

Validate the complete Library state:

```bash
python tools/validate_library.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Promotion invariants

Promotion is keyed by `(asset-id, version)` and never overwrites an existing immutable version.

A successful promotion:

1. re-runs normalization, testing, security and license gates;
2. copies the complete intake version under `modules/<asset-id>/<version>/`;
3. marks the copied manifest `certified`;
4. adds one catalog entry;
5. increments the catalog patch version;
6. removes the intake version only after module and catalog writes succeed.

A repeated call after successful promotion is an idempotent no-op.

If a filesystem/catalog write fails during promotion, the tool attempts to restore the previous catalog and remove the partial module copy. CI remains the final repository-level integrity check.

## Policy blocks

Automatic certification deliberately fails when:

- validation evidence is insufficient;
- security review is incomplete;
- known vulnerabilities are recorded;
- immutable external provenance is missing;
- external license evidence is missing;
- a strong/network-copyleft license requires an explicit project-level decision;
- a duplicate immutable version already exists in an inconsistent state.

These are not bypasses to hide in configuration. Any future override mechanism must be explicit, auditable and recorded as a policy decision.

## Tests

The repository test suite covers:

- no skipped lifecycle states;
- test-evidence gate;
- known-vulnerability rejection;
- restricted-license rejection;
- non-mutating dry-run;
- successful promotion;
- catalog version update;
- idempotent re-run;
- end-to-end validation of the promoted repository state with the main Library validator.
