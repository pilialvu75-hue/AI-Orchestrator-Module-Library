# Aivexus ResourceExchange v1

Status: canonical coordination contract for persisted cross-domain asset requests.
Owner of persistence hooks and shared contract integration: `cantiere`.
Domain producers/consumers: `aivexus-3d`, `aivexus-games`, and explicitly claimed adapters.

## Boundary

Resource exchange does not create a second project lifecycle and does not imply chat-to-chat communication.
Every request and result belongs to an existing Cantiere project and revision, is persisted, and is recoverable from canonical/project state.

The first 2D game milestone must not depend on the availability of 3D assets.

## Persistent request

Each request records at minimum:

- `requestId`: stable idempotent identifier.
- `requesterProjectId` and `requesterSpecRevision`.
- `producerDomain` and `consumerDomain`.
- `requestedRole` and `requestedFormat`.
- `requirements`: bounded semantic requirements, including units/coordinate conventions where relevant.
- `sourceRefs`: immutable input refs with SHA-256 when inputs already exist.
- `licenseRequirement`: accepted license/provenance constraints; never infer a license.
- `status`: requested, accepted, produced, rejected, unavailable, superseded or cancelled.
- `createdAt`, `updatedAt`, and the owning Cantiere job/checkpoint ref.

Retries reuse the same request identity for the same project/revision/operation/input/toolchain and must not duplicate the logical request.

## Produced result

A produced result records at minimum:

- `requestId`.
- `producerProjectId` and `producerSpecRevision`.
- `artifactRef`.
- `role`, `format`, `mimeType`, `sizeBytes`, `sha256`.
- `licenseRef` plus provenance/source attribution when applicable.
- `transformations`: scale, axis, unit, compression/conversion or other material transforms actually performed.
- `generator`: tool/adapter name, version and job ref.
- `result`: produced, rejected or unavailable with a stable reason code.
- `validationRefs`: persisted verification receipts.

The consumer must verify the artifact hash before use. A later project revision does not silently mutate an older artifact; a new revision produces a new immutable result/ref.

## Verification receipts

Receipts are persistent references, not prose claims. A receipt identifies:

- artifact/request ref and expected SHA-256;
- verifier/tool and version;
- check type (schema, file parse, geometry, build, browser runtime, target runtime, license/provenance);
- target/environment when relevant;
- PASS/FAIL/UNKNOWN result;
- timestamp and evidence ref.

UNKNOWN is never promoted to PASS. CI does not substitute for Fusion opening, physical print, playable browser execution or S24 FE target validation.

## Integration

- Cantiere owns persistence, attachment references, ProjectExtension integration and request/result lifecycle hooks.
- Library is queried before regenerating reusable capabilities/assets and remains the certification boundary for reusable code.
- Diagnostics stores or references closed verification receipts without exposing private prompts, project files, credentials or raw assets.
- Researcher code never executes directly in Cantiere.
- Cross-domain workers do not modify the shared storage/router/ProjectExtension files unless Cantiere explicitly hands over a bounded claim with matching locks.
