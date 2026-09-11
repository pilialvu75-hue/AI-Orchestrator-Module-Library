# Operational observations

Certified module directories are immutable. Runtime/integration experience is stored here instead.

Layout:

```text
observations/
  <asset-id>/
    <version>.json
```

Each file follows `schemas/asset.observations.schema.json` and is an append-only event ledger for exactly one catalogued module version.

Use `tools/library_history.py` rather than editing event history manually.

Examples:

```bash
python tools/library_history.py record voice.sherpa_stt 2.4.1 \
  --event-id project-a-voice-integration-1 \
  --type integration \
  --source cantiere \
  --outcome success \
  --target android \
  --contract-id voice.stt.v1 \
  --project-id project-a

python tools/library_history.py summary voice.sherpa_stt 2.4.1
python tools/library_history.py compare voice.sherpa_stt
```

The exact same `event_id` and content may be submitted repeatedly without duplicating history. Reusing an existing event id with different content is rejected.

Observation files are validated by `tools/validate_history.py` in CI.
