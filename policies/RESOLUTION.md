# Candidate Resolution and Offline Cache Policy

The Library resolver answers a narrow question:

> Which certified Library assets are eligible and best-ranked for a requested Lego capability?

It does **not** decide whether the Cantiere should reuse an asset instead of implementing something fresh. That economic decision remains a Cantiere responsibility because it depends on the current project and adaptation cost.

## Hard eligibility filters

Normal resolution considers only catalog entries that:

- are `certified`;
- are `active` by default;
- provide the requested capability;
- provide the requested contract when one is specified;
- support the requested target when one is specified;
- satisfy optional kind and maximum-integration-effort constraints.

`revoked` versions are never selectable.

`deprecated` versions are excluded by default and require an explicit `include_deprecated` request.

A caller may require stable contracts. In that mode, candidates attached only to draft/non-stable connector contracts are excluded.

## Transparent ranking — balanced-v1

After hard filtering, eligible candidates are ranked by `balanced-v1`.

The score is intentionally decomposed and returned to the caller:

- certification-time validation: 45%
- estimated integration effort: 25%
- smoothed observed integration reliability: 20%
- amount of operational evidence: 10%

Integration effort maps to:

- trivial: 1.0
- low: 0.8
- medium: 0.5
- high: 0.2

Observed reliability uses a conservative prior:

`(successful_integrations + 1) / (integration_attempts + 2)`

so a module with one lucky success is not treated as perfectly reliable.

Evidence confidence reaches 1.0 after five recorded integration attempts.

Active candidates always sort before explicitly included deprecated candidates. Remaining deterministic tie-breakers use evidence count, Semantic Version precedence and stable asset id ordering.

The output includes components, weights and evidence so the Cantiere can explain why one candidate ranked above another.

## No "latest wins" rule

A newer Semantic Version is only a late tie-breaker. Newer does not mean better for every target.

Operational evidence, validation and integration effort are first-class signals.

## Exact inspection

`get <asset-id> <version>` returns one exact catalogued version even if deprecated/revoked. This supports audits and pinned-project inspection without making the version eligible for new selection.

## Offline snapshot

`export-cache` produces a deterministic JSON snapshot for offline consumers.

The snapshot contains:

- Library and catalog version;
- contract registry;
- needs list;
- lifecycle revision;
- every certified asset, including deprecated/revoked versions for awareness;
- provenance, validation, security and integration metadata;
- connector/payload metadata;
- derived operational observations;
- ranking components;
- manifest and complete module-tree SHA-256 hashes.

It intentionally does **not** embed the full module source tree. Module transfer/fetch is a separate bridge concern.

The snapshot has no current-clock field. Identical Library state therefore generates identical snapshot bytes/content and identical `snapshot_sha256`.

## Integrity

`snapshot_sha256` hashes the canonical snapshot payload excluding the hash field itself.

Each asset also carries:

- `manifest_sha256`
- `module_tree_sha256`

The future Cantiere bridge can reject stale/corrupted cache or module content before assembly.

## CLI examples

```bash
python tools/library_resolver.py query \
  --capability voice.stt \
  --contract voice.stt.v1 \
  --target android

python tools/library_resolver.py resolve \
  --capability voice.stt \
  --contract voice.stt.v1 \
  --target android \
  --max-effort low \
  --require-stable-contract

python tools/library_resolver.py get voice.sherpa_stt 2.4.1

python tools/library_resolver.py export-cache \
  --output /tmp/module-library.json

python tools/validate_snapshot.py /tmp/module-library.json
```
