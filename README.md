# AI Orchestrator Module Library

Private reusable-asset library for the AI Orchestrator Cantiere/App Factory.

## System topology

`Cantiere -> Module Library <- Researcher`

The Module Library is the authoritative exchange store. Cantiere and Researcher do not depend on each other directly.

- **Cantiere** reads certified assets when they reduce real integration cost, and deposits newly created reusable assets after successful validation.
- **Researcher** is a separate autonomous project/service. It reads the Library needs list, searches open-source ecosystems, compares candidates and submits normalized candidates.
- **Module Library** stores reusable assets, versions, provenance, validation evidence, compatibility, licenses, security state and deprecation/revocation status.

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

Only `certified` assets are eligible for automatic Cantiere reuse.

## Reuse rule

An asset is reused only when its estimated total integration/adaptation cost is lower than fresh generation/implementation and it satisfies target, capability, connector, dependency, license, security and validation requirements.

A match is never reused merely because it exists.

## Durable state

- `catalog/index.json` — authoritative catalog of version-pinned reusable assets
- `catalog/needs.json` — machine-readable list of capabilities the Library currently wants the Researcher to improve/fill
- Git history — immutable audit trail for catalog/contract evolution

## Repository layout

- `catalog/` — machine-readable catalog + needs queue
- `modules/` — promoted versioned reusable assets
- `intake/` — submissions arriving from Researcher or Cantiere before certification
- `schemas/` — manifest/catalog/needs/Lego contracts
- `policies/` — acceptance, connector and versioning rules
- `examples/` — canonical submission examples
- `tools/` — deterministic repository validators
- `benchmarks/` — reproducible comparison/validation evidence retained with accepted assets
- `licenses/` — preserved third-party notices when required

## Researcher boundary

The Researcher never certifies its own discoveries. It submits candidates through `intake/` using the same manifest + Lego connector envelope used by Cantiere-originated assets.

When all current Library needs are covered, the Researcher should revisit the list and look for better, safer, faster or easier-to-integrate alternatives.

## Relationship with Ai-orchestrator-riserva

`Ai-orchestrator-riserva` owns project planning, approval, workspace mutation, adaptation, validation and final build.

The future bridge will let the Cantiere derive a capability shopping list from an approved project, query this Library, pin exact asset versions, assemble/adapt selected pieces, and submit reusable verified work back through Library intake.

## Validation

Repository changes are checked by `tools/validate_library.py` and `.github/workflows/validate-library.yml`.

The validator rejects duplicate needs/assets, malformed versions, catalog/manifest mismatches, connector inconsistencies and uncertified module-state errors before the Library is consumed by the Cantiere.
