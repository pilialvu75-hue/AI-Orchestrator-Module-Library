# Library Versioning Policy

The library versions three different things independently.

## 1. Asset version

Each reusable asset uses semantic versioning: `MAJOR.MINOR.PATCH`.

- `PATCH` — bug/security/implementation fix that preserves the public connector contract.
- `MINOR` — backward-compatible capability improvement.
- `MAJOR` — breaking behavior, requirements or integration changes.

A published historical version is never overwritten. New work creates a new version directory and manifest.

## 2. Connector contract version

The logical interface exposed by an asset is versioned independently from the implementation.

Example:

- asset: `voice.sherpa_stt@2.4.1`
- provided contract: `voice.stt.v1` / contract version `1.2`

Several different assets may implement the same connector contract and therefore compete for the same Cantiere slot.

Breaking interface changes create a new contract generation (for example `voice.stt.v2`).

## 3. Catalog version

`catalog/index.json` has its own semantic `catalog_version`. It changes when the machine-readable catalog contract or certified inventory meaningfully changes.

## Upgrade behavior

An application is never silently moved to a newer module merely because a newer one exists. The Cantiere must compare compatibility, migration cost, security and project tests before upgrading.

Known-good application builds remain reproducible by pinning exact asset id + version + provenance.

## Deprecation and revocation

- `deprecated`: still traceable and potentially usable for an existing pinned project, but not preferred for new work.
- `revoked`: must not be selected for new work. Existing projects should be flagged for review/replacement.

A replacement reference should be recorded where available.
