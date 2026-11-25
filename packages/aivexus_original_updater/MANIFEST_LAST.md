# Manifest-last consumer configuration

For the Starter Pack Android publication template (#403), the release asset is uploaded and remotely verified before the manifest is advanced. The original checker normally compares GitHub release metadata with the manifest. That fallback would allow a release to be found before the publication gate completes.

Consumers using manifest-last publication MUST explicitly set `manifestOnly: true` and `requireApkSha256: true` on UpdateChecker, and `requireApkSha256: true` on UpdateManager. The old two-source behavior remains the default for existing consumers. This option only changes discovery source, not signature or installer validation. Test with the configured feed; never use another application's feed. Physical OTA is pending.
