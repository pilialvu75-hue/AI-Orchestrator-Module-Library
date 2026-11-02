# P0 independent reviewer acceptance gates

Related issue: #219.

The existing review workflow emits unsigned requests and OSV advisory evidence. These outputs are not security approval and must not authorize certification.

A future independent reviewer must verify exact immutable source and CI identities, original license bytes, dependency inventory and real advisory responses. Scanner failures must fail closed. It must inspect privacy, source boundaries and static security risks, record reproducible evidence and only then consider a signed decision.

The review job must not run untrusted candidate code with signing credentials. The builder must never possess the reviewer private key. The protected certification workflow must validate signed statements against its repository-controlled public key and canonical source, SBOM and license digests.

Acceptance requires a new external candidate, different from the manually selected logging demo, to complete unattended discovery, acquisition, isolated testing, independent review, certification and a separate consumer integration test. Each stage must provide correlated GitHub run IDs and immutable hashes. Until then the candidate remains TESTED or BLOCKED, never CERTIFIED.

## Reviewer trust boundary and protected delivery

The current `review-autonomous-public-dart.yml` is an **unsigned evidence producer** with `contents: read`; it must never be granted a signing key or repository write permissions. Its artifacts are untrusted inputs until independently revalidated. The existing `certify-intake.yml` has `contents: write` to publish approved catalog changes; it must not also perform the independent review or possess the private reviewer key.

An independent reviewer implementation must meet all of these conditions before being enabled:

1. Run trusted reviewer code from a pinned, protected revision. Never execute a candidate's Dart code or scripts in the signing context. Read source as data only, with symlink/path/size protections.
2. Use a separately controlled signing identity and protected environment. Untrusted pull requests, forks, worker branches and `workflow_run` payloads must not gain access to the private key, even indirectly through command injection or artifact paths.
3. Recompute canonical payload, original license and SBOM hashes from the exact materialized source. Bind the verified immutable upstream commit, candidate identity/version, successful exact-head test CI, and the OSV scan's request digest and timestamp.
4. Independently decide license attribution/redistribution, source safety and privacy/data-flow boundaries. Any unknown, incomplete or contradictory evidence is BLOCKED, not APPROVED. Static scan findings require an explicit reviewer disposition; an empty findings list is not a security approval.
5. Produce a machine-readable immutable receipt for each decision, including scanner versions, evidence digests, run identities, review policy version and reasons. Only an APPROVED decision backed by complete checks may be signed.
6. Sign the exact canonical statement required by `library_review_attestation.py` using a key unavailable to Researcher, Builder and certification publishing jobs. The protected publisher receives only the signed statement and evidence, never the private key.
7. Before publication, the certification workflow rechecks signature with `LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM`, canonical source, license and SBOM digests, candidate identity and policy gates. No signature, mismatched evidence or unavailable trust anchor means no certification.
8. A separately permissioned consumer job must resolve the **published certified** artifact, verify its version/hash, run positive and negative functional assertions against real code, and retain correlated logs/run IDs. Do not count the manually selected logging demo or an isolated intake adapter as the P0 consumer proof.

### Operational acceptance checks

- Negative tests: unsigned approval, altered payload/license/SBOM, forged or stale CI identity, missing OSV response, malformed static audit, signing key exposure attempt, untrusted artifact path, and consumer artifact mismatch all fail closed.
- A successful test on Linux proves Linux only; Android, Windows and macOS require their own executed evidence.
- Enabling an independent signing service requires separate credential provisioning and branch/environment protection. Until these controls and an end-to-end unattended run are verified, report TESTED/BLOCKED, never CERTIFIED or CONSUMER_VERIFIED.
