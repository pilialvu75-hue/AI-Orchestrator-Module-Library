# Original updater: standalone development distribution

Status: experimental, not production-certified. Source engine unchanged; pinned package commit `c715ff93324371f923666a0766035b02b20530ea`. The three desktop regression jobs passed in run 45595456287. Android physical OTA, formal license/security review, rollback and extracted reusable settings UI are not certified.

The [first-party preview register](../catalog/first-party-preview.json) is deliberately separate from the authoritative certified catalog and resolver. Do not resolve as a production package or claim certification.

Download the **aivexus-original-updater-0.1.0-dev.1** Actions artifact from a successful [standalone export run](https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library/actions/workflows/export-original-updater.yml). Verify the inner ZIP with SHA256SUMS.txt (PowerShell: Get-FileHash -Algorithm SHA256). Extract into your application's vendor/aivexus_original_updater directory. The package includes its original tests and provenance, but no other Library module. Use this Flutter dependency:

```yaml
dependencies:
  aivexus_original_updater:
    path: vendor/aivexus_original_updater
```

Commit or reproducibly fetch the exact verified vendor package before running flutter pub get. This avoids cloning the entire Library on Windows. Retain SOURCE-COMMIT.txt and SHA256SUMS.txt for traceability. The Actions artifact expires after 30 days; rerun the workflow to reproduce the pinned archive. Do not treat a checksum as a signature.

Each application supplies its own feed, repository, installer names and native host bridge. No Beta Access or Diagnostics enrollment is imposed by the package. Never point a consumer at the Riserva test fixture. RendezVous is the first physical OTA pilot; preserve VoiceBridge unchanged. See the package README for API details.
