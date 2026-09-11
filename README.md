# AI Orchestrator Module Library

Private reusable-asset library for the AI Orchestrator Cantiere/App Factory.

## System topology

`Cantiere -> Module Library <- Researcher`

The Module Library is the authoritative store. It does not perform open-source discovery itself.

- **Cantiere** reads certified assets when they reduce real integration cost, and deposits newly created assets only after successful validation.
- **Researcher** searches open-source ecosystems, compares candidates and proposes qualified assets to this library.
- **Module Library** stores accepted reusable assets, metadata, versions, provenance, validation evidence, compatibility, licenses and deprecation status.

## Purpose

The Cantiere should **reuse proven software before generating new software**. This repository stores reusable assets that have passed the relevant admission and validation gates.

## Asset classes

- `module` — reusable implementation with a stable contract
- `component` — smaller reusable UI/domain/utility unit
- `integration_bundle` — subsystem requiring adapters/configuration, for example voice or inference
- `architecture_pattern` — validated structure/recipe rather than portable source
- `project_template` — larger starting point for a new application
- `policy_bundle` — reusable security/privacy/hardening rules and tests

## Library lifecycle

`submitted -> quarantined -> normalized -> tested -> certified -> deprecated/revoked`

Only `certified` assets are eligible for automatic Cantiere reuse.

## Reuse rule

An asset is reused only when its estimated total integration/adaptation cost is lower than fresh generation/implementation and it satisfies target, capability, license, security and validation requirements. A local match is never reused merely because it exists.

## Repository layout

- `catalog/` — machine-readable index of certified assets
- `modules/` — certified reusable assets or pinned internal implementations
- `intake/` — submissions arriving from the Researcher or Cantiere before certification
- `schemas/` — manifest schemas
- `policies/` — admission, licensing, security and deprecation policies
- `benchmarks/` — reproducible comparison/validation results retained with accepted assets
- `licenses/` — preserved third-party notices when required

## Researcher boundary

Open-source discovery, candidate collection and candidate-to-candidate comparison belong in the separate Researcher repository. This library receives only structured submissions with immutable upstream provenance, license data, evidence and test/benchmark material.

## Relationship with Ai-orchestrator-riserva

`Ai-orchestrator-riserva` owns project planning, approval, workspace mutation, adaptation, validation and final build. After project approval, the Cantiere derives a capability shopping list, queries this certified catalog and reuses only assets that beat fresh work on compatibility, quality, time and resource cost.

Generated Cantiere work can be submitted back into this library only after successful validation/emission, preserving provenance and version history.
