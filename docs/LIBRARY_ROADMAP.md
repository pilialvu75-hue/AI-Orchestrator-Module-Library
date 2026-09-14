# Module Library Delivery Roadmap

The Module Library is the authoritative reusable-asset exchange between Cantiere and the independent Researcher.

System topology:

`Cantiere -> Module Library <- Researcher`

## V1 delivery status

- [x] Reuse foundation in Cantiere (`Ai-orchestrator-riserva` #316)
- [x] Separate Library and Researcher responsibilities/repositories
- [x] Durable Library catalog, needs list, manifest schema and Lego connector foundation
- [x] Library CI validator for catalog, needs and contract references
- [x] Capture/promotion pipeline with one-step lifecycle gates, dry-run, immutable promotion and catalog registration
- [x] Immutable SemVer history and append-only operational observations
- [x] Deprecation/revocation/reinstatement audit and rollback planning
- [x] Deterministic resolver, transparent ranking, exact-version lookup and integrity-protected offline snapshot
- [x] Cantiere capability shopping list after project approval
- [x] Reuse-first Cantiere planner against Library candidates
- [x] Safe Cantiere assembly/adaptation into the project workspace
- [x] Cantiere verified-output capture and fail-closed Library intake submission path
- [x] Credential-free intake envelope plus GitHub Device Flow authenticated transport to the private Library
- [x] Library materialization of verified Cantiere intake bundles
- [x] Certified package export for Cantiere consumption
- [x] Cantiere snapshot/package verification and exact-pin consumption
- [x] Researcher per-capability status and restart-safe/idempotent Library intake
- [x] App Modules dashboard with Library-authoritative certified counts and separate Researcher progress
- [x] Event-driven Library certification autopilot; no mandatory cron or paid worker
- [x] Fail-closed production smoke: a real Researcher Drift intake reaches Library main but is not promoted without test/security evidence
- [x] Certification evidence is local, identity-bound and integrity checked before `tested`/`certified`
- [x] Deterministic CI E2E proves eligible discovered intake -> tested -> certified -> catalog -> snapshot/package export

## What V1 completion means

V1 completion means the **Library engine and exchange contracts are operational and safe**. It does not mean every need already has two certified implementations.

`catalog/needs.json` intentionally remains a living demand queue. Catalog population continues after V1 through normal operation:

1. Researcher submits immutable candidates as `discovered`.
2. Library validation/security evidence is attached.
3. The Library autopilot advances only eligible candidates and promotes them to immutable `modules/` entries.
4. Cantiere consumes only certified, non-revoked exact versions.
5. Cantiere observations feed later quality/evolution decisions.

The production Drift smoke is intentionally still non-certified until real execution/security evidence exists. A release must never be manufactured by changing `tests_passed` or `security.reviewed` without evidence.

## After V1

The following are evolution/population work rather than blockers for the deterministic V1 core:

- increase coverage toward the desired candidate count for each capability;
- run target-specific validation for shortlisted open-source candidates;
- collect real reuse success/failure observations from emitted apps;
- refine cost accounting with operational data;
- add the V1.5 AI Curator/Advisor above the deterministic core without transferring certification authority to AI.
