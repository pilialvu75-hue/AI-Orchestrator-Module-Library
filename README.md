# AI Orchestrator Module Library

Private reusable-asset library for the AI Orchestrator Cantiere/App Factory.

## Purpose

The Cantiere should **reuse proven software before generating new software**. This repository stores certified reusable assets and research candidates with provenance, compatibility, license, validation, benchmark and security metadata.

The library is not a dump of copied source code. External open-source projects enter as **candidates** first; only assets that satisfy the acceptance policy can be promoted to the certified catalog.

## Asset classes

- `module` — reusable implementation with a stable contract
- `component` — smaller reusable UI/domain/utility unit
- `integration_bundle` — subsystem requiring adapters/configuration (for example voice or inference)
- `architecture_pattern` — validated structure/recipe rather than portable source
- `project_template` — larger starting point for a new application
- `policy_bundle` — reusable security/privacy/hardening rules and tests

## Lifecycle

`discovered -> quarantined -> normalized -> tested -> certified -> deprecated/revoked`

Only `certified` assets are eligible for automatic Cantiere reuse.

## Reuse rule

An asset is reused only when its estimated total integration cost is lower than fresh generation/implementation and it satisfies target, capability, license, security and validation requirements. A local match is never reused merely because it exists.

## Repository layout

- `catalog/` — machine-readable index of certified assets
- `modules/` — certified reusable assets or pinned internal implementations
- `candidates/` — research dossiers for external candidates; no automatic execution
- `schemas/` — manifest schemas
- `policies/` — admission, licensing, security and deprecation policies
- `benchmarks/` — reproducible comparison results
- `licenses/` — preserved third-party notices when required

## Researcher contract

The module researcher discovers multiple independent candidates for common capabilities, records the exact upstream repository and commit/tag, checks license/maintenance/security signals, and prepares a reproducible test dossier. It does **not** silently vendor arbitrary internet code into applications.

The preferred pattern is to keep upstream code referenced by immutable commit/tag while it is a candidate, then vendor or adapt only the minimal certified asset when the license and integration model permit it.

## Relationship with Ai-orchestrator-riserva

`Ai-orchestrator-riserva` owns planning, approval, workspace mutation, validation and final build. This repository is the reusable supply store. The Cantiere creates a capability shopping list after project approval, queries the certified catalog, and reuses only assets that beat fresh work on compatibility, quality, time and resource cost.

Generated Cantiere work can be promoted back into this library only after successful validation/emission, preserving provenance and version history.
