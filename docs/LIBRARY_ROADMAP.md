# Module Library Delivery Roadmap

The Module Library is developed before Cantiere integration. The independent Researcher evolves in its own repository and communicates only through Library contracts/intake.

## Priority order

1. **Library** — make storage, contracts, certification and versioning authoritative and safe.
2. **Cantiere** — prepare shopping-list/reuse/assembly behavior against stable Library contracts.
3. **Cantiere <-> Library** — connect read/cache/fetch/deposit flows after both sides are stable.
4. **Researcher** — independent supplier that reads Library needs and submits candidates through intake; never a direct Cantiere dependency.

## Unified roadmap

- [x] Reuse foundation in Cantiere (`Ai-orchestrator-riserva` #316)
- [x] Separate Library and Researcher responsibilities/repositories
- [x] Durable Library catalog, needs list, manifest schema and Lego connector foundation
- [x] Library CI validator for catalog, needs and contract references
- [x] **Capture/Promotion pipeline**: gated intake lifecycle, dry-run, certification, immutable promotion, catalog registration, idempotency and E2E tests
- [ ] Versioning/evolution policy and historical quality/compatibility records
- [ ] Deprecation/revocation/rollback mechanics
- [ ] Library query/resolution API/CLI suitable for Cantiere and offline cache generation
- [ ] Cantiere capability shopping list after project approval
- [ ] Planner reuse-first against Library candidates
- [ ] Assembly/adaptation into project workspace
- [ ] Cantiere capture gate and deposit back to Library intake
- [ ] Cost/AI accounting and reuse success metrics
- [ ] Cantiere UI explaining reused assets, versions and provenance
- [ ] Full E2E: Project A -> Library -> Project B reuse without unnecessary generation

This file is intentionally about delivery order, not the deeper long-term module vision. New architecture ideas should be added only when they do not destabilize the current step-by-step implementation.
