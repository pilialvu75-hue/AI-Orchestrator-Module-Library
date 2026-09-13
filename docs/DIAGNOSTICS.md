# Module Library shared Diagnostics producer

The Module Library publishes only filtered technical events to the shared public repository `pilialvu75-hue/Ai-orchestrator-diagnostics`.

## Namespace

Each stable Library instance owns one release namespace:

- release tag: `diagnostics-library-v1-<instance-id>`
- archive asset: `library-diag-<sha256>.jsonl`
- latest asset: `library-latest.jsonl`
- event schema: `ai-orchestrator.diagnostics.event.v2`

The producer is `tools/library_diagnostics.py`. It must never write to Android `diagnostics-v1-*`, Researcher `diagnostics-researcher-v1-*`, or assets belonging to another producer.

## Credential

Publishing requires the environment variable `AI_ORCHESTRATOR_DIAGNOSTICS_TOKEN`.

Use a dedicated fine-grained GitHub token restricted to `pilialvu75-hue/Ai-orchestrator-diagnostics` with only the repository permission needed to create/update Releases and assets (`Contents: read/write`). Store it in the producer's secure secret store. Never commit it, print it, reuse the normal Library/Researcher credential, or paste it into chat.

The publisher fails closed when the variable is missing.

## Manual publish

Example technical heartbeat:

```bash
AI_ORCHESTRATOR_DIAGNOSTICS_TOKEN=... \
python tools/library_diagnostics.py \
  --instance library-primary \
  --producer-version "$(git rev-parse HEAD)" \
  --platform github-actions \
  --run manual-001 \
  --event LIBRARY_DIAGNOSTICS_HEARTBEAT \
  --severity info \
  --field status=ok
```

Use `--dry-run` to validate and print the filtered JSONL without any network write.

A publish is successful only after the publisher verifies the remote archive and `library-latest.jsonl`. Operationally, also verify the corresponding `diagnostics-library-v1-<instance-id>` release through the GitHub API before declaring the integration active.

## Privacy and format

Only structured technical fields are accepted. Credentials, authorization data, cookies, prompts, conversations, raw payloads, API keys and private keys are rejected. Nested/unbounded fields are rejected as well.

Every event records producer, producer version/commit, platform, stable instance, session or run, RFC3339 timestamp with timezone, event and severity. Optional correlation identifiers and bounded scalar fields are allowed.

## Idempotency and retention

Archive filenames are content-addressed with SHA-256. A retry reuses an already uploaded archive when name/state/size match. Release assets are discovered with pagination.

Limits:

- maximum archive file: 1 MiB
- maximum producer archive budget: 20 MiB per Library instance/release
- `library-latest.jsonl`: bounded recent view only, not authoritative history

Rotation can delete only assets matching `library-diag-<sha256>.jsonl` inside the Library-owned release. It must not perform global cleanup and must never remove Android or Researcher releases/assets.

## Cost policy

There is no recurring Diagnostics workflow in this repository. This is intentional: the current project policy is zero mandatory operating cost. Publishing is manual or invoked by a deliberately chosen zero-cost producer environment. A future scheduled runner must remain opt-in and must not silently consume paid services or private-repository Actions minutes.

## Shared contract

The authoritative cross-producer contract lives in `pilialvu75-hue/Ai-orchestrator-diagnostics`:

- `docs/PRODUCERS.md`
- `schemas/diagnostic-event-v2.schema.json`

The Android app keeps its existing legacy release/asset format for compatibility. Library and Researcher use separate namespaces and must not overwrite one another.
