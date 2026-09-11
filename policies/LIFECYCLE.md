# Certified Asset Lifecycle Policy

Certified module contents are immutable. Post-certification availability is therefore tracked in the catalog, not by rewriting `modules/<asset-id>/<version>/manifest.json`.

## Availability states

A catalogued certified version has one current availability state:

- `active` — eligible for normal resolution and new projects;
- `deprecated` — retained and traceable, but not selected by default for new work;
- `revoked` — forbidden for new work and excluded from rollback candidates.

For compact/legacy catalog entries without an explicit `availability` field, `active` is the default.

## Allowed transitions

```text
active -> deprecated
active -> revoked
deprecated -> active
deprecated -> revoked
```

A revoked version is not reinstated by the normal lifecycle command. Revocation is deliberately sticky because it commonly represents a security, legal or severe correctness decision. Correction should normally use a new fixed version; exceptional reversal requires an explicit repository-level policy change/review.

## Audit ledger

Every lifecycle transition is appended to `catalog/lifecycle.json` with:

- stable event id;
- asset id + version;
- previous and next state;
- timestamp;
- reason;
- source;
- optional replacement asset/version.

The ledger is validated against the current catalog so catalog state cannot silently drift away from the transition history.

## Replacement

A deprecated or revoked asset may point to a replacement. The replacement must already exist in the catalog and must not itself be revoked.

Replacement may be:

- a newer version of the same asset lineage;
- a different implementation that exposes the required Lego contract.

## Rollback planning

Rollback is a recommendation/planning operation, never a silent application mutation.

`tools/library_lifecycle.py rollback-plan` searches older versions of the same asset id and, by default:

- accepts only `active` versions;
- rejects revoked versions;
- can constrain target platform and contract id;
- orders candidates by Semantic Version precedence;
- includes operational observation summaries when available;
- returns `automatic_switch_performed=false`.

Deprecated versions can be included only through an explicit option because they may still be useful in emergency/manual recovery but should not be the normal first choice.

The future Cantiere integration must still run project-level validation before applying a rollback.

## Commands

```bash
python tools/library_lifecycle.py deprecate <asset-id> <version> \
  --reason "reason" \
  --replacement <asset-id>@<version>

python tools/library_lifecycle.py revoke <asset-id> <version> \
  --reason "reason" \
  --source security

python tools/library_lifecycle.py reinstate <asset-id> <version> \
  --reason "reason"

python tools/library_lifecycle.py rollback-plan <asset-id> <from-version> \
  --target android \
  --contract-id voice.stt.v1
```

All catalog/lifecycle changes must pass `tools/validate_lifecycle.py` and the normal Library CI before consumption.
