# Library intake readiness — automated evidence backlog

The Library currently has two separate supply states:

- **Certified catalog** (`catalog/index.json`): source-backed, version-pinned modules usable by Cantiere after target/cost checks.
- **Untrusted intake** (`intake/*/*/manifest.json`): discovered candidate references. Their presence is **not** certification.

On 18 October 2026, the repository had **3 certified catalog entries and
19 manifest-only first-party intake candidates**. Every intake candidate
lacked attributable license evidence, a local pinned source snapshot,
reproducible test evidence, and a completed independent security review.
The upstream certification workflow deliberately skips manifest-only source
references; it does not imply those candidates were tested and failed.

## Automated backlog

`tools/library_intake_readiness.py` reads all intake manifests and builds a
deterministic `catalog/intake-readiness.json`. The existing first-party
quarantine workflow refreshes this report whenever intake, needs or certified
catalog metadata changes and on its six-hour schedule. The report is stable
across repeat runs: no ever-changing timestamps or unnecessary commits.

Each candidate carries a version, lifecycle state, immutable source pointer,
explicit missing-evidence codes, and next actions. The report also groups
needs by high-priority coverage, with both total certified candidates and
**per-platform certified counts**, so a module tested for Linux cannot be
counted as covering Android or Web.

An inventory row is **never** an executable approval:
`independent_certification_authorized=false` for all intake candidates, even
if a manifest supplies a positive boolean. The report reads metadata and
checks file presence only; it does not execute untrusted code or authenticate
test execution, SBOM provenance, license, or reviewer decisions.

## Real path to additional modules

1. Obtain an immutable, attributable source snapshot from the pinned commit
   through a read-only stage with no permission to write certified modules.
2. Resolve upstream license and preserve the correct license file. Do not
   relabel `NOASSERTION` as MIT or otherwise invent permissions; copyleft
   obligations may require explicit review.
3. Run the relevant target-specific tests and static analysis **without
   repository write permission**. Attach a source/commit/target-bound receipt.
4. Independently produce a security report and SBOM, assess vulnerabilities
   and integration costs, and preserve the platform boundaries.
5. Pass the existing lifecycle and promotion policy before any immutable
   `modules/<id>/<version>/` and catalog entry is written.
6. Confirm the new version is consumable through the Library resolver and
   package exports; never equate CI success with physical runtime success.

The `library-researcher` claim and repair workflow are separate. This
report is owned by Library-side inventory automation and must **not** release
or overwrite Researcher's claim.

## Operations

Generate a report locally or inside a protected Actions runner:

```bash
python -m tools.library_intake_readiness --output catalog/intake-readiness.json
```

GitHub Actions runs the report under `Library First-Party Quarantine Triage`;
its write allowlist permits only the previously allowlisted quarantine
manifests plus `catalog/intake-readiness.json`. The report is also attached
as a workflow artifact and displayed in the run summary. Failure to read
canonical manifests fails closed; nothing is silently certified.

**The next meaningful success metric is a new properly certified module,
not a new report row.** This backlog identifies the concrete missing proofs
to obtain before promoting one.
