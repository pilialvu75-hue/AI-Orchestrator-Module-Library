# Module Library V1.5 — AI Curator / Advisor

## Status

Ring 1 foundation.

The Curator is an advisory layer above the deterministic Module Library core. It may reason over sanitized Library context, but it is never an authority for certification, security, lifecycle, compatibility or repository mutation.

Topology:

`Researcher -> deterministic Library Core -> AI Curator -> deterministic verification -> Cantiere`

The Curator can improve semantic matching and explanation without weakening the V1 safety model.

## Authority boundary

The deterministic Library core remains the only authority for:

- lifecycle transitions and certification;
- immutable versioning and integrity hashes;
- compatibility and contract checks;
- license/security gates;
- deprecation, revocation and rollback state;
- catalog/package/snapshot writes.

The Curator is allowed to:

- identify capability coverage gaps;
- rank or compare known candidates;
- flag possible duplicates;
- suggest adapters;
- surface health/quality concerns;
- recommend an already-active certified asset for reuse.

The Curator is not allowed to:

- certify or revoke anything;
- create or modify catalog/module/intake state;
- bypass deterministic eligibility checks;
- turn an intake candidate into a reusable asset;
- invent asset IDs, versions or capabilities that are absent from its request context.

## Provider contract

`tools/library_curator.py` defines the provider-neutral `LibraryCuratorProvider` protocol.

A provider receives only a sanitized request using:

- `schemas/library.curator.request.schema.json`

and must return:

- `schemas/library.curator.response.schema.json`

The provider has no repository handle, no write callback and no access to Library credentials through this interface.

## Data minimization

The request builder sends only fields required for advisory reasoning:

- capability needs and targets;
- asset identity/version/source area;
- lifecycle/availability state;
- capability/platform/contract metadata;
- upstream repository/commit/license identity;
- high-level validation/security state;
- integration effort/constraints.

It intentionally excludes local evidence paths, SBOM contents, test reports, security notes, adapter notes and unrelated repository data.

## Deterministic response verification

Every provider response is checked before the caller sees it as verified advice:

- request ID must match;
- only the response contract fields are accepted;
- cited assets/capabilities must exist in the exact request context;
- confidence must be in `[0, 1]`;
- unsupported mutation-like fields fail closed;
- `reuse_recommendation` is accepted only for an asset stored under `modules/` with `status=certified` and `availability=active`.

An uncertified Researcher/Cantiere intake may be compared or ranked, but the Curator cannot recommend it as reusable production material.

## First provider

The architecture is intentionally provider-neutral. The first network implementation will be Gemini through an API-backed adapter in the next V1.5 ring.

No Gemini credential, API endpoint or model-specific behavior is introduced in Ring 1. This keeps the authority boundary independently testable before a live network dependency is added.

## Next ring

Ring 2 will add one Gemini adapter behind `LibraryCuratorProvider`, strict JSON response handling, timeout/error accounting and zero-secret logging. The deterministic request builder and response verifier in this Ring remain unchanged.
