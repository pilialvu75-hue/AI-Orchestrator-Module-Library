# Certified Modules

Only promoted, versioned reusable assets live here.

Canonical layout:

```text
modules/
  <asset-id>/
    <version>/
      manifest.json
      payload/
      tests/
      provenance/
      benchmark/
```

Rules:

1. A certified version is immutable.
2. The manifest must implement the standard Lego connector.
3. `catalog/index.json` is the authoritative machine-readable inventory.
4. Payloads must preserve provenance and licensing obligations.
5. Revocation/deprecation changes catalog/manifest status; historical source remains traceable.
6. The Cantiere consumes exact `asset-id + version`, never `latest` as an implicit production dependency.
