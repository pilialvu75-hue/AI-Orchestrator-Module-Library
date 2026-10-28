# Independent review of materialized module source (v1)

Materialized source under `payload.type=repository_path` **or**
`payload.type=upstream_reference` with a real pinned `payload/` snapshot
must never be certified merely because a worker writes
`security.reviewed=true` in a manifest or local JSON report. The protected
certification job validates a detached **Ed25519** signature from a
separately controlled reviewer identity. Historical reference-only assets
without materialized source remain under their existing legacy policy;
this does not retroactively assert their source was audited.

## Who can sign

The security reviewer generates and protects an Ed25519 private key **outside**
the Library, Researcher and Cantiere repositories. Only its corresponding
public key, in PEM `BEGIN PUBLIC KEY` format, is configured in the Library
repository Actions **variable**
`LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM`. The protected `main`
`certify-intake.yml` workflow injects that key into the verification process.

The value is NOT read from PR files, the candidate manifest, SBOM, test
reports, or arbitrary environment variables supplied by worker requests.
The private key must never be committed, added to a workflow artifact,
placed in chat, or shared with build workers.

Until that repository variable exists, **every signed local certification
fails closed**. Existing upstream-reference legacy assets are not migrated
or retrospectively reapproved.

## Signed statement

A verified, independent reviewer must assemble and check all evidence and
then sign the following JSON object (all fields mandatory):

```json
{
  "schema": "ai-orchestrator.library-review-authorization.v1",
  "asset_id": "module.id",
  "version": "0.1.0",
  "source_commit": "40 lower-case hex characters",
  "payload_sha256": "64 lower-case hex characters of the real source tree",
  "sbom_sha256": "64 lower-case hex characters of the exact SBOM file",
  "license_file_sha256": "64 lower-case hex characters of the attributable license file",
  "reviewed_at": "ISO timestamp",
  "reviewer_id": "independent security reviewer",
  "known_vulnerabilities": 0,
  "decision": "APPROVED"
}
```

The exact bytes signed are ASCII:

```
AI-ORCHESTRATOR-LOCAL-REVIEW-v1\n
<compact JSON of the statement with sorted keys, no spaces, ensure_ascii=True>\n
```

The statement is placed in `security/review.json` as
`independent_attestation.statement` with
`algorithm: "ed25519-openssl-v1"` and `signature_base64` containing the
64-byte Ed25519 signature. The ordinary review report must also supply its
existing `schema`, matching `asset_id`, `version`, `source_commit`,
`reviewed: true`, `known_vulnerabilities: 0`, `sbom_sha256` and the
additional matching `reviewed_at`, `reviewer_id`, `decision: "APPROVED"`,
and `payload_sha256`.

The local manifest's `security.reviewed_at` and
`provenance.license_file` must match the signed review. The verifier
recomputes the source tree, license file and SBOM checksums. A stale, changed
or unsigned report is rejected even if all tests passed and the worker
declared itself reviewed.

This verifies the authenticity of a specific **review assertion**. It is
not itself proof that a license was actually granted, that the source has
zero vulnerabilities, or that the target runtime is working. The separate
reviewer must examine those facts before signing.

## Status of the first Dart candidate

`diagnostics.logging.library.privacy_events@0.1.0` has source-bound
Dart analysis, self-tests and adversarial redaction tests on three desktop
operating systems. Its deterministic, read-only review request can be
generated with:

```sh
python tools/library_privacy_review_packet.py --output /tmp/privacy-review.json
```

The request is **not a signed approval**. The candidate remains in
`tested`, pending an explicit license decision and independent signed
security review. No automatic certification or Android/iOS runtime claim
is made by adding this verification protocol.

## Recovery and negative tests

The library CI runs `test_library_review_attestation.py` with a throwaway
test-only private/public key pair. Tests cover authenticated sign-off,
missing trusted key, forged reviewer identity, tampered source, license,
SBOM, altered vulnerability counts and invalid signature algorithms.
Real reviewer private key material never enters CI.

## Current external Swift candidate — security not approved (28 Oct 2026)

`diagnostics.logging.avdlee.diagnostics@0.1.0` is genuinely **tested**
on macOS (53 upstream package tests plus 5 Aivexus logging bridge tests);
the original source commit and bridge template SHA-256 are pinned in the
independently GitHub-job-verified test report.

The independent security-preflight record at
`intake/diagnostics.logging.avdlee.diagnostics/0.1.0/evidence/security-preflight.json`
contains a CycloneDX dependency inventory, pinned dependency license evidence
and an OSV snapshot. The recorded scan returned no matching advisories, **not
proof of absence of vulnerabilities**. The upstream logger intercepts process
`stdout/stderr`, reads process environment and starts system metrics monitoring.
Reviewers must assess privacy consent, redaction before collection, platform
permissions, data retention, exception/exit handling and entitlement effects,
as well as the **Aivexus adapter source**, before considering sign-off.

This preflight is not a signed approval. Keep `security.reviewed=false`
and `certification_authorized=false` until the independent reviewer examines
the complete delivered artifact, tests real runtime permissions and signs the
exact, immutable source/SBOM/license evidence with the separately controlled
key. A compatible *production package* containing the tested adapter source is
also required: a manifest or an upstream reference alone is not deliverable code.
