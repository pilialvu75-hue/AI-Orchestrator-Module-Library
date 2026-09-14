# Module Library V1.5 — AI Curator / Advisor

## Status

Ring 1 foundation complete. Ring 2 Gemini provider implemented.

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

## Ring 2 — Gemini provider

`tools/library_curator_gemini.py` implements the first and only V1.5 network provider behind the same `LibraryCuratorProvider` contract.

Current defaults:

- provider: Gemini API;
- stable default model: `gemini-3.6-flash`;
- endpoint family: Gemini `models.generateContent`;
- structured JSON output using Gemini response schema support;
- timeout: 30 seconds;
- retries: up to 2 for 429/5xx transient failures;
- request size cap: 512 KiB;
- response size cap: 1 MiB.

The model can be changed without changing the Curator contract by setting:

```bash
AI_ORCHESTRATOR_CURATOR_GEMINI_MODEL=gemini-3.7-flash
```

The API credential is read only from the process environment:

```bash
GEMINI_API_KEY=...
```

It is sent only in the `x-goog-api-key` HTTP header. It is never placed in the URL, request body, Library state or Curator result. Error messages intentionally omit response bodies and credentials.

A manual invocation is available through:

```bash
GEMINI_API_KEY=... python tools/run_curator_gemini.py \
  --task rank_candidates \
  --capability storage.local_db
```

The command prints a verified Curator result. The result is advisory; running it does not write to the Library.

CI does not call the live Gemini API and does not require a Gemini secret. Provider behavior is tested with an injected transport, including structured output parsing, transient retry behavior, non-retryable failures and secret placement.

## Next rings

Ring 3 adds semantic capability matching and explainable ranking behavior on top of this provider. Ring 4 adds duplicate/alternative/adapter suggestions, Ring 5 uses operational observations for health reasoning, and Ring 6 surfaces clearly labeled AI advice in the Cantiere/Modules UI.
