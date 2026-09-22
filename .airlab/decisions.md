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
