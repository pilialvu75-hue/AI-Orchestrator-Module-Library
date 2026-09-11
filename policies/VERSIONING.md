# Asset Versioning and Evolution Policy

The Library versions implementation artifacts, Lego connector contracts and the catalog independently.

## 1. Immutable asset versions

Each reusable implementation lineage has a stable `asset_id` and Semantic Version:

`MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`

Guideline:

- `PATCH` — compatible bug/security/implementation/performance fix;
- `MINOR` — backward-compatible capability improvement;
- `MAJOR` — intentionally incompatible behavior, requirements, configuration or integration change.

A certified historical version is never overwritten. `modules/<asset-id>/<version>/` is a historical fact.

Different implementations of the same Lego contract use different asset ids. They remain interchangeable candidates because they provide the same capability/contract, not because they belong to one implementation lineage.

Example:

```text
voice.sherpa_stt@2.4.1 -> voice.stt.v1
voice.whisper_stt@1.8.0 -> voice.stt.v1
```

## 2. Connector contract versions

The logical interface exposed by an asset is versioned independently from its implementation.

Several assets may implement the same connector contract and compete for the same Cantiere slot.

Breaking logical-interface changes create a new contract generation, for example `voice.stt.v2`.

## 3. Catalog version

`catalog/index.json` has its own semantic `catalog_version`. Inventory mutations advance that version without rewriting historical module versions.

## No silent upgrades

An application is never moved to a newer module merely because a newer one exists.

The Cantiere may later recommend an upgrade, but it must evaluate compatibility, adaptation/migration cost, security, operational evidence and project tests first.

Known-good application builds remain reproducible by pinning exact asset id + version + provenance.

## Certification-time vs operational evidence

The immutable module manifest contains certification-time facts such as provenance, dependencies, validation score, tested platforms, connector contracts and security review.

Later real-world experience MUST NOT mutate the certified module merely to update counters. It is stored separately under:

```text
observations/<asset-id>/<version>.json
```

Examples:

- successful/failed Cantiere integrations;
- observed target/contract compatibility;
- later revalidation results;
- benchmark observations;
- incidents/regressions.

This resolves an important tension: module versions stay reproducible while the Library can still learn from every use.

## Append-only history semantics

Observation files are append-only event ledgers.

Every event has a stable `event_id`.

- sending the exact same event again is an idempotent no-op;
- reusing an existing event id with different content is an error;
- `revision` equals the number of recorded events and detects destructive edits.

Operational summaries such as reuse count, successful integrations, failed integrations, success rate and latest compatibility are derived from events instead of becoming mutable source-of-truth counters inside the module.

## Version comparison

Version ordering follows Semantic Version precedence, including prereleases. Build metadata does not alter precedence.

Comparison tooling may display every catalogued version together with observed quality. The latest semantic version is not automatically assumed to be the best version for every target/project.

## Deprecation, revocation and rollback

- `deprecated`: still traceable and potentially usable for a pinned existing project, but not preferred for new work;
- `revoked`: must not be selected for new work; pinned projects must be flagged for replacement/review.

The concrete deprecation/revocation/rollback mechanics are the next dedicated roadmap step. Old versions and their observations remain traceable throughout those transitions.
