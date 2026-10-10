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


## Automated claim leases and projection

Decision date: 2026-10-01

- Worker claims are time-bounded leases with heartbeat, not permanent locks.
- Default lease is 12 hours and the maximum lease is 24 hours unless the canonical policy is explicitly changed.
- Duplicate active `work_item` claims are invalid across lanes.
- An expired lease is never treated as success and is never silently reassigned. Reconciliation clears the stale claim, marks the lane `BLOCKED`, records an expiry event and requires Main/Reviewer reconciliation.
- `tools/control_plane_manager.py` is the deterministic claim/heartbeat/release/reconcile/project implementation.
- `.github/workflows/control-plane-reconcile.yml` reconciles on relevant main changes and hourly, with serialized execution and bounded retry on push races.
- The global `canonical-state.json#projection` is derived from merged lane state. It is only rewritten when the source digest changes, avoiding timestamp-only commit churn.
- The reconciliation automation cannot promote worker output to `VERIFIED` or `DONE`; promotion authority remains with Main/Reviewer.


## Chat rollover and historical deletion policy

Decision date: 2026-10-01

- Chat conversations are execution surfaces, not authoritative project storage.
- When a chat is full, a replacement chat reuses the same canonical lane and reads current repository state through the generated lane bootstrap.
- No new project state or parallel roadmap is created merely because the conversation changes.
- A historical chat becomes deletion-safe only after its unique actionable work, unresolved items, reusable evidence and architectural decisions have a canonical repository home.
- The private registry `.airlab/control-plane/historical-chat-consolidation.json` records the deletion decision and migration rationale for recovered legacy chats.
- Ongoing chats may remain temporarily as bridges, but their backlog is duplicated into canonical workstream/roadmap state before they are considered replaceable.


## Resource-level conflict locks

Decision date: 2026-10-02

- Active claims own explicit machine-readable resource locks in addition to their unique `work_item` identity.
- Resource-lock authority is global across canonical lanes. Two different work items may not concurrently own the same lock key.
- Lock keys are namespaced and stable: examples include `file:<repo>:<path>`, `contract:<name>`, `resource:<name>`, `scope:<name>` and `pr:<repo>#<number>`.
- A declared branch is automatically represented by `branch:<repo>:<branch>`, preventing two lanes from writing the same branch under different work-item names.
- Different resource keys remain parallelizable; this hardening serializes only declared overlap rather than globally serializing all platform work.
- Resource locks live on the active claim, persist through `REVIEW_REQUIRED` and reviewer rework, and are released only when the claim is released/accepted or stale ownership is reconciled.
- An expired but unreconciled claim continues to block its resources. Reconciliation records its lock set before clearing the claim and blocking the stale lane for reviewer attention.
- Transactional inbox compare-and-swap remains the operational mutation path; resource locks close the cross-lane race that independent lane state versions cannot detect.


## Canonical automation ownership registry

Decision date: 2026-10-02

- External scheduler state is not control-plane authority. An automation may be enabled outside the repository and still have zero canonical write permission.
- `.airlab/control-plane/automation-registry.json` is the machine-readable authorization registry for scheduled/conditional control-plane actors.
- Every mutation-inbox request requires a non-empty `actor_id`. Any `automation:` actor must be registered exactly once, enabled canonically, hold `control_plane_mutation`, and be allowed for both the requested operation and target-lane policy.
- Reviewer automation is constrained to worker review transitions and may not claim, implement or mutate its owner `main-reviewer` lane. This makes the prior Reviewer takeover failure structurally rejectable rather than prompt-dependent.
- Lane-worker automations are owner-lane scoped. Read-only reporters/watchers have no control-plane mutation operations. Disabled canonical writers remain registered as disabled so stale executions fail closed.
- The GitHub reconcile workflow is a system processor, not a work-item owner: it may apply authorized inbox requests, reconcile stale leases and rebuild projections, but cannot originate implementation work or promote worker results.
- Authorization is enforced at mutation ingress before lane compare-and-swap/application. A rejected automation request is quarantined without mutating canonical lane state.

## Aivexus Studio 3D / Videogiochi bootstrap

Decision date: 2026-10-10

- Canonical worker lanes are `aivexus-3d` and `aivexus-games`, both targeting `pilialvu75-hue/Ai-orchestrator-riserva`.
- Cantiere is the **single owner** of the shared Aivexus base: ProjectExtension v1, conservative project persistence/migration, attachment-store interface, project-type selector and shared navigation/router integration.
- Domain workers do not fork or duplicate that base. Shared changes are requested from Cantiere and serialized by `contract:aivexus-project-extension-v1`, `contract:aivexus-resource-exchange-v1` and exact shared-file locks.
- `platform-web` keeps `Ai_orchestrator-prova` as its primary repository and gains Riserva as a secondary authorized repository only for explicitly claimed Aivexus/browser adapter work. AIrLab remains provider-neutral and does not become a second Project/Execution authority.
- Resource exchange between 3D and games is persistent, not conversational. Requests/results record project and spec revision, requested/produced format, immutable artifact hash, license/provenance, result status and persistent verification receipts.
- The consumer verifies SHA-256 before use. Revisions never silently overwrite older artifacts.
- Library remains the reuse/certification boundary; Diagnostics carries closed evidence/verification references; Researcher code never executes directly in Cantiere.
- `AIVEXUS-GAME-1` depends on the shared Cantiere base but **does not depend on `AIVEXUS-CAD-1` or any 3D asset**. The first 2D game must be buildable with original/licensed 2D resources.
- Registration and coherent documentation do not make CAD runners, Godot export, Fusion compatibility, browser gameplay or physical print operational. Those require their own claims, implementation and runtime/target evidence.
