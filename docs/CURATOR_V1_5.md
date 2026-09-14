# Module Library V1.5 — AI Curator / Advisor

## Status

Rings 1-5 implemented: provider-neutral authority boundary, Gemini provider, semantic/explainable ranking, duplicate/alternative/adapter analysis, and observation-backed health reasoning.

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

The Curator is allowed to identify coverage gaps, rank known candidates, flag possible duplicates or alternatives, suggest adapters, surface health concerns and recommend only already-active certified assets for reuse.

The Curator is not allowed to certify/revoke anything, mutate catalog/module/intake state, bypass deterministic gates, turn an intake candidate into reusable material, or invent assets/capabilities absent from the supplied context.

## Provider contract and data minimization

`tools/library_curator.py` defines the provider-neutral `LibraryCuratorProvider`. Requests use `schemas/library.curator.request.schema.json`; responses use `schemas/library.curator.response.schema.json`.

Only advisory metadata is sent: needs/targets, asset identity/version/source area, lifecycle/availability, capabilities/platforms/contracts, upstream repository/commit/license identity, high-level validation/security state and integration effort/constraints. Evidence paths, SBOM contents, test reports, security notes, adapter notes, credentials and unrelated repository data are excluded.

For health review, only a bounded sanitized observation view is added: aggregate integration/incident/validation/compatibility counters, deterministic health signals, and at most the 20 most recent event outcomes. Observation `notes`, `metadata` and `project_id` are never sent to the AI provider.

Every response is deterministically verified: request ID, supported fields, known refs/capabilities and confidence ranges are checked. A `reuse_recommendation` is accepted only for an active certified asset under `modules/`.

## Ring 2 — Gemini provider

`tools/library_curator_gemini.py` is the first and only V1.5 network provider. Default model is `gemini-3.6-flash`, model-overridable without changing the Curator contract. It uses structured JSON output, a 30-second timeout, up to two retries for transient 429/5xx failures, a 512 KiB request cap and 1 MiB response cap.

`GEMINI_API_KEY` is read only from runtime environment and sent only through `x-goog-api-key`; it is never placed in URL, body, Library state or returned results. CI uses injected transports rather than live Gemini calls.

`.github/workflows/run-curator-gemini.yml` is a manual, phone-friendly, read-only execution path. It has `contents: read`, no schedule, no persisted Git credential and requires one repository Actions secret named `GEMINI_API_KEY`. Verified advisory output is retained as a seven-day artifact.

## Ring 3 — semantic matching and explainable ranking

`tools/library_curator_semantic.py` ranks one capability at a time. When candidates exist, every candidate must appear exactly once. Six transparent advisory factors are returned per asset: `semantic_fit`, `target_fit`, `contract_fit`, `evidence_strength`, `integration_fit`, and `overall`, each constrained to `[0,1]`, plus a concise observable rationale.

The deterministic core verifies exact candidate coverage, factor/ref alignment and non-increasing overall score order. Intake candidates may be evaluated but are never made reusable by ranking. With zero candidates, the service skips Gemini entirely and emits a deterministic coverage gap.

## Ring 4 — duplicates, alternatives and adapters

`tools/library_curator_relations.py` adds two higher-level services without changing Library authority.

### Duplicate / alternative analysis

All assets that provide the selected capability are deterministically known **alternative candidates**. AI is used only when at least two alternatives exist, to flag subsets that appear duplicate or near-duplicate from supplied metadata.

A duplicate hint must:

- cite at least two exact known asset refs;
- use only refs from the selected capability context;
- remain an advisory similarity signal, never a lifecycle or reuse decision.

When fewer than two candidates exist, the AI call is skipped because duplicate analysis cannot add information.

### Adapter analysis

Adapter analysis is run only when at least one candidate exists. Every accepted `adapter_hint` must cite at least one exact known asset and contain at least one concrete `adapter_suggestions` entry. The AI may describe a bridge required by declared contracts/platforms/constraints, but it cannot create files or mutate the Cantiere/Library workspace.

Both services expose whether AI was actually called and preserve a deterministic list of the alternative candidates considered. Tests verify insufficient-candidate short-circuits, malformed duplicate/adapter hints, exact known references and no Library mutation.

## Ring 5 — observations and health reasoning

`tools/library_curator_health.py` reasons over the append-only operational ledger without granting the AI any lifecycle authority.

The deterministic core first derives factual health signals for each certified Library module, including:

- observed integration failures;
- low integration success rate after enough attempts;
- recent consecutive integration failures;
- recorded incidents;
- incompatible compatibility observations;
- latest validation failure/warning or low score;
- absence of operational history.

Gemini is called only when at least one signal indicates actual degradation beyond simple lack of history. A returned `health_warning` is accepted only when it cites exact known module refs that already have deterministic health signals. Health output cannot contain ranking factors or adapter suggestions and cannot change availability, certification, revocation or any repository state.

Health requests expose only aggregate facts plus a maximum of 20 sanitized recent events. Project IDs, free-form notes and event metadata are deliberately removed before the provider boundary. Tests verify healthy short-circuiting, degrading-module warnings, privacy stripping, deterministic signal binding and no Library mutation.

## Next ring

Ring 6 surfaces clearly labeled AI advice in the Cantiere/Modules UI. The deterministic Library state remains visually and logically separate from Curator advice.
