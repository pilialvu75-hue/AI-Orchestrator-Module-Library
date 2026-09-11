# Intake

This directory is the only write-entry point for new external/internal reusable-asset candidates before certification.

Sources may include:

- the independent Researcher;
- the Cantiere after a successful project/task;
- a manual import.

Each submission must have its own directory containing at least a `manifest.json` that follows `schemas/module.manifest.schema.json` and the standard Lego connector contract.

Suggested layout:

```text
intake/
  <asset-id>/
    <version>/
      manifest.json
      payload/
      tests/
      provenance/
```

A submission in `intake/` is never automatically trusted or automatically reused by the Cantiere. It must pass normalization, validation, security/license review and promotion first.

Promotion moves/copies the accepted immutable version under `modules/<asset-id>/<version>/` and adds it to `catalog/index.json`.
