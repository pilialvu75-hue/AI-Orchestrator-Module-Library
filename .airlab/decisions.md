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

## 2026-09-27 — Riserva roadmap executor

- The owner authorized the ChatGPT scheduled task **Avanza roadmap Riserva** to
  advance the existing Riserva roadmap, using bounded implementation PRs and
  current GitHub evidence.
- The private operating contract is
  `.airlab/public-repositories/Ai-orchestrator-riserva/autonomy.md` on main.
- Mutable execution checkpoints live at
  `.airlab/public-repositories/Ai-orchestrator-riserva/execution.json` on the
  dedicated `automation/riserva-state` branch. This branch is operational state,
  not a code branch to merge; ordinary checkpoint writes must not trigger builds.
- Conditional blob-SHA writes and expiring leases coordinate this executor's
  runs. Other chats still require explicit PR/head checks: this is not a global
  lock over every contributor.
- Roadmap completion still requires acceptance evidence. Existing physical
  validation, certification, release, privacy and approval requirements remain
  applicable. No additional spending or paid API activation is authorized.
