# Intake

This directory is the only write-entry point for new external/internal reusable-asset candidates before certification.

Sources may include:

- the independent Researcher;
- the Cantiere after a successful project/task;
- a manual import.

Each submission has its own immutable-version directory containing at least a `manifest.json` that follows `schemas/module.manifest.schema.json` and the standard Lego connector contract.

```text
intake/
  <asset-id>/
    <version>/
      manifest.json
      payload/
      tests/
      provenance/
```

A submission in `intake/` is never trusted or reused automatically by the Cantiere.

## Lifecycle

Creating the intake directory is the submission event. The manifest itself advances one state at a time:

```text
discovered -> quarantined -> normalized -> tested
```

Use the repository pipeline so states cannot be skipped:

```bash
python tools/library_pipeline.py advance <asset-id> <version> quarantined
python tools/library_pipeline.py advance <asset-id> <version> normalized
python tools/library_pipeline.py advance <asset-id> <version> tested
```

Each transition enforces the gates relevant to that stage. In particular, normalization requires coherent provenance/payload/Lego metadata and `tested` requires real validation evidence.

## Certification / promotion

Certification is a separate operation. First run a dry-run:

```bash
python tools/library_pipeline.py promote <asset-id> <version> --dry-run
```

Then, after review:

```bash
python tools/library_pipeline.py promote <asset-id> <version>
python tools/validate_library.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

A successful promotion:

- re-checks certification gates;
- creates `modules/<asset-id>/<version>/`;
- marks the promoted copy `certified`;
- updates `catalog/index.json`;
- removes the corresponding intake version only after successful writes;
- never overwrites an existing immutable version;
- is idempotent when repeated after a completed promotion.

Strong/network-copyleft licenses and candidates with known vulnerabilities are blocked from **automatic** certification and require an explicit higher-level decision instead of a hidden override.
