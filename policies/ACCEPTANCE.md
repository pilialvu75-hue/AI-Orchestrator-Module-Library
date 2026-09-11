# Reusable Asset Acceptance Policy

An asset may be promoted to `certified` only when all required gates pass.

## Lifecycle

Repository submission is represented by the presence of an immutable candidate version under `intake/<asset-id>/<version>/`.

The manifest then advances one state at a time:

`discovered -> quarantined -> normalized -> tested -> certified`

`certified` is not written directly inside `intake/`: certification is performed only by the promotion pipeline, which creates the immutable version under `modules/` and registers it in `catalog/index.json`.

Later lifecycle states are:

`certified -> deprecated -> revoked`

A version is never overwritten in place by a newer implementation. Improvements use a new semantic version.

## Required gates

1. **Provenance**
   - Exact origin is known.
   - External assets pin an immutable upstream commit.
   - Required copyright/license notices are preserved with the candidate.

2. **License**
   - License is identified before source is vendored or adapted.
   - The license is compatible with the intended distribution model.
   - Strong-copyleft/network-copyleft obligations are never silently accepted; they require an explicit project-level decision and are blocked from automatic certification.

3. **Functional validation**
   - Reproducible tests pass.
   - Validation score is at least `0.80`.
   - Validation time and tested target/platform are recorded.

4. **Security**
   - No secrets or credentials are embedded.
   - Dependencies are enumerated and pinned where appropriate.
   - Known vulnerabilities and security constraints are recorded.
   - Automatic certification is blocked when known vulnerabilities remain.
   - High-risk code is never auto-promoted.

5. **Integration economics**
   - Reuse is expected to cost less time/resources than fresh implementation.
   - Hidden migration, adapter or dependency costs are included in the estimate.

6. **Contract stability**
   - Every advertised capability maps to an `ai-orchestrator-lego` contract registered by the Library.
   - Public entry points and required configuration are documented.
   - Platform-specific behavior is explicit.

## External candidate rule

Finding a repository on the internet is not certification. Researcher/Cantiere/manual submissions enter through `intake/` and remain untrusted until normalized, tested and promoted.

The independent Researcher should normally collect at least two credible candidates for important/common capabilities so alternatives can be compared on quality, maintenance, security, license and integration cost. Candidate discovery does not grant certification.

## Promotion

Promotion is immutable by `(asset_id, version)`.

The promotion pipeline:

1. accepts only a `tested` intake asset;
2. re-checks provenance, payload, Lego connector, functional evidence, security and license gates;
3. refuses duplicate immutable versions;
4. supports a non-mutating dry-run;
5. copies the accepted version to `modules/<asset-id>/<version>/`;
6. changes only the promoted copy to `certified`;
7. appends a deterministic catalog entry and bumps the catalog patch version;
8. removes the corresponding intake version only after catalog/module writes succeed;
9. treats a repeated promotion of an already-certified/catalogued version as a successful no-op.

The working-tree operation is designed to be committed as one repository change. Repository CI then validates the resulting complete state.

## Automatic Cantiere reuse

Automatic reuse is allowed only for `certified` assets.

The Cantiere must still reject a certified module when the current app target, capability requirements, license constraints, security policy or integration-cost threshold are not satisfied.
