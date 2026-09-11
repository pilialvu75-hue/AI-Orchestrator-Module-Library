# Reusable Asset Acceptance Policy

An asset may be promoted to `certified` only when all required gates pass.

## Required gates

1. **Provenance**
   - Exact origin is known.
   - External assets pin an immutable upstream commit/tag.
   - Required copyright/license notices are preserved.

2. **License**
   - License is identified before source is vendored or adapted.
   - The license is compatible with the intended distribution model.
   - Strong-copyleft/network-copyleft obligations are never silently accepted; they require an explicit project-level decision.

3. **Functional validation**
   - Reproducible tests pass.
   - Validation score is at least `0.80`.
   - Target/platform compatibility is recorded.

4. **Security**
   - No secrets or credentials are embedded.
   - Dependencies are enumerated and pinned where appropriate.
   - Known vulnerabilities and security constraints are recorded.
   - High-risk code is not auto-promoted.

5. **Integration economics**
   - Reuse is expected to cost less time/resources than fresh implementation.
   - Hidden migration, adapter or dependency costs are included in the estimate.

6. **Contract stability**
   - Public entry points and required configuration are documented.
   - Platform-specific behavior is explicit.

## External candidate rule

Finding a repository on the internet is not certification. Research candidates remain in `candidates/` until normalized and tested. The researcher should normally collect at least two independent candidates for important/common capabilities so the Cantiere can compare quality, maintenance, security, license and integration cost.

## Promotion

Promotion is immutable by version. Improvements create a new semantic version; they do not overwrite the historical certified implementation. A certified asset may later be marked `deprecated` or `revoked` while remaining traceable.

## Automatic Cantiere reuse

Automatic reuse is allowed only for `certified` assets. The Cantiere must still reject a certified module when the current app target, capability requirements, license constraints, security policy or integration-cost threshold are not satisfied.
