# AI Orchestrator Module Library

Private reusable-asset library for the AI Orchestrator Cantiere/App Factory.

## System topology

`Cantiere -> Module Library <- Researcher`

The Module Library is the authoritative exchange store. Cantiere and Researcher do not depend on each other directly.

- **Cantiere** reads certified assets when they reduce real integration cost, and deposits newly created reusable assets after successful validation.
- **Researcher** is a separate autonomous project/service. It reads the Library needs list, searches open-source ecosystems, compares candidates and submits normalized candidates.
- **Module Library** stores reusable assets, immutable versions, provenance, validation evidence, operational history, compatibility, licenses, security state and deprecation/revocation status.

See `ARCHITECTURE.md` for the complete boundary definition.

## Purpose

The Cantiere should **reuse proven software before generating new software**, but only when reuse is genuinely cheaper/safer than fresh implementation.

The Library provides the durable, versioned and machine-readable supply layer that makes this possible.

## Lego interchange standard

Every reusable asset exposes the same exchange envelope through `schemas/lego.connector.schema.json`.

The Cantiere selects pieces by **capability + connector contract**, not by project-specific filenames.

Example:

`voice.stt -> voice.stt.v1`

Multiple certified implementations can therefore compete for the same logical slot and be swapped after compatibility, migration-cost and project-test checks.

See `policies/LEGO_CONNECTOR.md`.

## Asset classes

- `module` — reusable implementation with a stable contract
- `component` — smaller reusable UI/domain/utility unit
- `integration_bundle` — subsystem requiring adapters/configuration, for example voice or inference
- `architecture_pattern` — validated structure/recipe rather than portable source
- `project_template` — larger starting point for a new application
- `policy_bundle` — reusable security/privacy/hardening rules and tests

## Library lifecycle

`discovered -> quarantined -> normalized -> tested -> certified -> deprecated/revoked`

Only `certified` assets are eligible for normal reuse. Certified content is immutable; post-certification selection state (`active`, `deprecated`, `revoked`) is tracked separately and audited.

## Reuse rule

An asset is reused only when its estimated total integration/adaptation cost is lower than fresh generation/implementation and it satisfies target, capability, connector, dependency, license, security and validation requirements.

A match is never reused merely because it exists.

The Library resolver ranks **eligible Library candidates only**. The later Cantiere decision still compares reuse against fresh implementation for the current project.

## Query and resolution

`tools/library_resolver.py` exposes the stable read side of the Library:

```bash
python tools/library_resolver.py query --capability voice.stt --contract voice.stt.v1 --target android
python tools/library_resolver.py resolve --capability voice.stt --contract voice.stt.v1 --target android
python tools/library_resolver.py get <asset-id> <version>
```

Normal resolution excludes deprecated and revoked assets. Deprecated candidates require explicit opt-in; revoked candidates are never selectable.

The transparent `balanced-v1` policy returns its score components/weights rather than hiding why one candidate ranked above another. See `policies/RESOLUTION.md`.

## Offline cache

A deterministic, integrity-protected read snapshot can be generated for future offline Cantiere use:

```bash
python tools/library_resolver.py export-cache --output /tmp/module-library.json
python tools/validate_snapshot.py /tmp/module-library.json
```

The snapshot contains contracts, needs, certified asset metadata, lifecycle state, operational summaries and SHA-256 integrity data. It does not duplicate the full module source tree; module transfer remains a separate bridge responsibility.

## Durable state

- `catalog/index.json` — authoritative catalog of version-pinned reusable assets
- `catalog/needs.json` — machine-readable list of capabilities the Library currently wants the Researcher to improve/fill
- `catalog/lifecycle.json` — append-only deprecation/revocation/reinstatement audit
- `modules/<asset-id>/<version>/` — immutable certified implementation versions
- `observations/<asset-id>/<version>.json` — append-only operational evidence learned after certification
- Git history — audit trail for catalog/contract/policy evolution

The immutable module is never rewritten merely to increase reuse counters or record a later compatibility result. Operational quality is derived from observations. See `policies/VERSIONING.md`.

## Repository layout

- `catalog/` — machine-readable catalog + needs queue + lifecycle ledger
- `modules/` — promoted immutable versioned reusable assets
- `intake/` — submissions arriving from Researcher or Cantiere before certification
- `observations/` — append-only per-version runtime/integration history
- `schemas/` — manifest/catalog/needs/Lego/history/snapshot contracts
- `policies/` — acceptance, connector, lifecycle, versioning and resolution rules
- `examples/` — canonical submission examples
- `tools/` — deterministic validators, lifecycle/history and query/cache tooling
- `benchmarks/` — reproducible comparison/validation evidence retained with accepted assets
- `licenses/` — preserved third-party notices when required

## Researcher boundary

The Researcher never certifies its own discoveries. It submits candidates through `intake/` using the same manifest + Lego connector envelope used by Cantiere-originated assets.

When all current Library needs are covered, the Researcher should revisit the list and look for better, safer, faster or easier-to-integrate alternatives according to its configured operating phase.

## Relationship with Ai-orchestrator-riserva

`Ai-orchestrator-riserva` owns project planning, approval, workspace mutation, adaptation, validation and final build.

The future bridge will let the Cantiere derive a capability shopping list from an approved project, consume the Library resolver/offline snapshot, pin exact asset versions, assemble/adapt selected pieces, report integration outcomes into `observations/`, and submit reusable verified work back through Library intake.

## Validation

Repository changes are checked by:

- `tools/validate_library.py` — catalog, needs, contracts and module/intake integrity;
- `tools/validate_history.py` — operational-history integrity;
- `tools/validate_lifecycle.py` — lifecycle ledger/catalog-selection consistency;
- `tools/validate_snapshot.py` — exported offline-cache integrity;
- `.github/workflows/validate-library.yml` — CI orchestration plus unit/integration tests and snapshot export.

The validators reject duplicate needs/assets, malformed versions, catalog/manifest mismatches, connector inconsistencies, invalid history/lifecycle state, uncertified module-state errors and corrupted snapshots before the Library is consumed by the Cantiere.
