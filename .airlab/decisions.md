# Private architecture decisions

Updated: 2026-09-22  
Reconstructed from historical project chats and current repository state.

## Authority and trust

- Module Library is the mandatory trust boundary for reusable code.
- Researcher and Cantiere may communicate directly only through a future structured, sanitized **control plane**; executable/source candidates from Researcher must pass through Library first.
- Cantiere can submit reusable code it created, but only to `intake/` as untrusted `discovered` material. It cannot self-certify.
- Researcher cannot promote directly into the certified catalog.
- Untrusted upstream execution must never share a job with Library write credentials.
- Cantiere remote build execution remains read-only, sparse-scoped and without persisted repository credentials.

## Learning and reuse

- A missing capability is actionable the **first time** Cantiere detects it.
- Cantiere continues building what the user needs while the capability gap is recorded for Researcher; Researcher does not block the current app.
- Any reusable capability Cantiere successfully creates is captured immediately for Library intake after the required validation/security evidence exists.
- Before generating a capability again, Cantiere must query certified Library state first.
- If Researcher later finds an external alternative to a Cantiere-created capability, Library may compare, version or retain both; certified state changes only through Library gates.

## Continuous application evolution

- Library must track the capability/module bill of materials for maintained applications.
- A better certified capability may create upgrade candidates for applications already using an older implementation.
- Cantiere may process those upgrades when idle, but an automatic rebuild is not an automatic release.
- CI, emulator and build success are insufficient for stable distribution.
- Real physical-device validation is mandatory before an evolved application becomes stable.
- Security/bugfix/compatibility changes may receive higher evolution priority than performance/features/refactors.

## Roadmap policy

- Persistent roadmap/state is stored only in private repositories for now.
- Future chats/agents must read `.airlab/handoff.md`, then roadmap/state/decisions before changing architecture.
- Roadmap state must be updated in the same PR when a roadmap item materially changes.


## Public repository roadmap storage

- Roadmaps for public repositories are stored privately under `.airlab/public-repositories/` in Module Library.
- Public repositories do not receive private roadmap/state files.
- Empty public placeholders are tracked privately so future chats do not confuse them with active repositories.

## First-party legacy mining

- Owner-controlled legacy private repositories are legitimate first-party source material for Researcher.
- They must be accessed through an explicit read-only allowlist.
- Mining is static/read-only by default; legacy source is not executed merely to decide whether it is reusable.
- Extracted code/patterns remain untrusted candidates and still enter Library intake/certification before reuse.
- Provenance back to the originating repository/commit is mandatory.


## Canonical multi-chat control plane

Decision date: 2026-10-01

- The private Module Library hosts the single coordination authority for the AI Orchestrator ecosystem under `.airlab/control-plane/`.
- Roadmaps remain continuously updated planning documents; workstream files represent current lane execution state; `canonical-state.json` is the global authority/projection.
- The Main/Reviewer lane owns cross-lane consolidation and is the only lane allowed to promote worker output to `VERIFIED` or `DONE`.
- Specialized worker chats may independently implement and collect evidence, but self-promotion stops at `REVIEW_REQUIRED`.
- Every bounded task must be claimed before implementation; overlapping active claims are invalid.
- CI green is only one gate. Runtime/hardware claims require target-runtime evidence and Diagnostics or equivalent receipts.
- Platform lanes share one Orchestrator and stable contracts. Inference implementations are deliberately target-specific: Windows, legacy Windows, Linux, macOS, iOS, Android, Web and Raspberry Pi may use different LLMs, sizes, quantizations, backends and acceleration settings when benchmark evidence justifies them. They must preserve shared inference/routing semantics, Diagnostics contracts and Cantiere lifecycle.
- A result is not DONE while roadmap or canonical state is stale.


## Target-specific inference architecture

Decision date: 2026-10-01

- Runtime Core owns the shared inference contract, routing semantics, streaming/cancellation/error behavior and model-profile schema.
- Each platform lane owns its actual inference profile for its hardware/software target.
- There is no mandatory universal local LLM, quantization, backend or accelerator configuration across platforms.
- A single platform may assign different models to different roles/capabilities.
- Selection is benchmark-gated using quality, first-content latency, total latency, decode throughput, memory/headroom, stability, thermal behavior, accelerator effectiveness, compatibility and practical storage/download cost.
- The objective is the strongest practical stable profile for the target, not the largest model and not the smallest model.
- Each practical local profile defines a lower-resource fallback.
- Main/Reviewer promotes a target inference profile only after target-runtime evidence and shared-contract compatibility are demonstrated.
