# Storage secrets — pinned upstream intake proposal

**State: `discovered`; do not use in Cantiere or a release.**

- Library issue: https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library/issues/127
- Library capability and draft contract: `storage.secrets` / `storage.secrets.v1` (v1.0, status `draft`)
- Pinned upstream package: `flutter_secure_storage` 11.2.0
- Upstream repository: https://github.com/juliansteenbakker/flutter_secure_storage
- Immutable upstream commit: `e8eeb449cd512b26153f0a3376dfe374dd39a999`
- Source entry: `flutter_secure_storage/lib/flutter_secure_storage.dart`
- Upstream manifest: `flutter_secure_storage/pubspec.yaml` at the exact commit, SDK >=3.8, Flutter >=3.19
- Android package requirement: Android API 23+ documented upstream. The AI Orchestrator target baseline must be checked, not inferred.
- License: BSD-3-Clause; unmodified upstream LICENSE at `provenance/LICENSE`

## Available source-only evidence

Researcher discovery and static upstream preflight have been run on GitHub Actions:

- https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Researcher/actions/runs/38982409403
- https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Researcher/actions/runs/38982734188

At the pinned commit the read-only Researcher preflight reported static security `CLEAR`, vulnerability `CLEAR`, vulnerability admission `true`, and 0 unresolved SBOM entries. This is not the Library's independent security review, and does not validate execution, runtime behavior or integration. No untrusted upstream source was executed by the Researcher.

## Minimum adapter contract to implement and test

Do not copy upstream code into the Library/Cantiere without an independent supply-chain decision. Prefer a pinned package dependency when justified by target toolchains.

- Define and test an abstract `SecretsStore` API for `read(key)`, `write(key,value)`, `delete(key)`, and key enumeration/availability only if the Library contract explicitly permits it.
- Specify null/missing key semantics, key scope/namespace, secret redaction in logs, and error normalization.
- Verify whether Android keystore/biometric mode, backed-up restored data, namespace switches, device reboot and cipher migration preserve confidentiality and recoverability.
- Reject any unapproved plaintext fallback. Explicitly handle locked/unavailable keystore, auth cancellation and failed writes, with no secret leakage.
- Validate Linux secret service, Windows and macOS keychain implementations independently; the upstream plugin manifest advertises these platforms, but this branch contains no physical/desktop proof.
- Re-evaluate Flutter/Dart toolchain compatibility in the actual Aivexus application, and ensure platform code does not fork shared orchestration contracts.
- Create adapter source, contract tests, end-to-end/negative tests and device/desktop receipts before changing `validation.tests_passed` or `security.reviewed`.

## Next authorized gates

1. Acquire a non-overlapping canonical Library intake claim for issue #127. The existing `library-researcher` claim on Researcher PR #98 cannot be silently repurposed.
2. Transition `discovered -> quarantined -> normalized -> tested` only through `tools/library_pipeline.py`, with all stage evidence.
3. Independently verify the source version, BSD redistribution notice, license obligations, SBOM, vulnerability scan and contract/target fit. The known vulnerabilities count here reflects the source preflight only.
4. After real validations, attach Library-owned test-report and security-review artifacts, preserving hash binding to the pinned SHA.
5. Run certification dry-run and independent promotion. Until then **the catalog remains unchanged**; Researcher must not dispatch upstream source straight to Cantiere.

The manifest `platforms` names candidate targets for future verification, **not validated support**. `validated_on` remains empty and the asset is not certified.


## Existing Aivexus integration and breaking-upgrade assessment (17 October 2026)

**Do not adopt as a new duplicate implementation.** At the Android repository main commit `40cb40fd8a0d7ca80d6656d9ee7524d57b5a16c4`:

- `pubspec.yaml` already specifies `flutter_secure_storage: ^10.3.1`, and `pubspec.lock` resolves **10.3.4**.
- The current lockfile requires **Dart >=3.12.0** and **Flutter >=3.44.0**; the broader application `pubspec.yaml` lower bounds (Dart >=3.4, Flutter >=3.22.2) are not evidence of actual CI toolchain incompatibility.
- `android/app/build.gradle` sets **minSdk 28**.
- Existing critical consumers include `lib/core/runtime/inference/cloud_credential_store.dart`, `lib/app_factory/workshop/workshop_library_github_auth.dart`, `lib/features/module_library/data/module_library_github_config.dart`, and `lib/core/diagnostics/github_diagnostics.dart`.
- The app already has two injected read/write/delete storage boundaries (`CloudSecretStorage` and `WorkshopLibrarySecretStorage`), as well as two direct plugin usages. Avoid introducing an independent third credential store before consolidating the existing boundaries.
- At pinned upstream 11.2.0, `flutter_secure_storage/CHANGELOG.md` warns that 11.0.0 removed deprecated cipher algorithms and options: data saved using removed algorithms/features may be unreadable after upgrade. Source's Android `resetOnError` defaults to **true**, which can erase data after an error. The changelog recommends migrating legacy data on v10 before moving to v11.

The evidence file `tests/migration-gates.json` records the initial versions and **ten pending gates**. All test fixtures must use freshly generated disposable fake tokens, without exposing token values or hashes in logs, CI, GitHub issues or diagnostics. Do not use real credentials during exploratory migration and do not assume rollback preserves an encrypted store after a schema/cipher upgrade. 

**Decision to resolve before implementation:** prefer certifying a reusable wrapper of the already operational v10.3.4 integration first, or plan a separately reviewed and physically tested 10.3.4 → 11.2.0 migration with backwards-compatible key semantics. The draft intake remains source-only and never upgrades the app on its own.

## Offline migration readiness (informational fail-closed gate)

The candidate includes an executable **static** gate, not a runtime test or promotion tool:

```bash
python intake/storage.secrets.researcher.flutter_secure_storage/0.1.0/tests/migration_readiness.py \
  --manifest intake/storage.secrets.researcher.flutter_secure_storage/0.1.0/manifest.json \
  --evidence intake/storage.secrets.researcher.flutter_secure_storage/0.1.0/tests/migration-gates.json
```

Expected current result: `BLOCKED` with eight pending migration gates. The report is safe to share because it contains only stage identifiers and version metadata, not credential contents. It does **not** fetch credentials, use network services, run Flutter, or execute untrusted upstream code.

A manually edited set of all-PASS flags yields at most `INDEPENDENT_REVIEW_REQUIRED`; it cannot declare certification or authorize an APK update. The checker is bound to the pinned Researcher commit and current four-consumer baseline; any change requires refreshing upstream provenance and the application audit. This gate is specific to the draft intake proposal and **does not modify or supersede the canonical Library pipeline**.


## Android 12+ backup/restore and upgrade preflight (issue #849)

The actual AI Orchestrator `android/app/src/main/AndroidManifest.xml` has no explicit `android:allowBackup`, `android:dataExtractionRules` or `android:fullBackupContent`. These source observations are **not proof** of the final merged APK policy: inspect the merged manifest and Android 12+ cloud/device transfer rules separately. A valid acceptance receipt shows that encrypted SharedPreferences cannot be restored without their corresponding Keystore material; use disposable fixtures only. See [Android #849](https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/issues/849).

At pinned upstream `11.2.0`, `FlutterSecureStorage.checkUpgradeStatus()` supplies a **read-only** pre-access report of `state`, `reason`, `entryCount` and `willDiscardOnNextAccess`. The static Library checker captures only the state fields/receipt, **never secret contents, hashes or raw diagnostic details**.

On a physically tested disposable installation, run this check **before** initializing any credential consumers. Do not read/write credentials when:
- `legacyDataUnreadable` or `legacyDataDiscarded` appears, including `removedCipher`, `missingAlgorithmMarkers` or `missingKeyMaterial`;
- `unknown` appears (e.g., authentication required), or a platform reports `ok` together with `unsupportedPlatform`;
- `willDiscardOnNextAccess` is true, because a subsequent read/write can permanently erase data if `resetOnError` remains enabled.

Even `ok/none` plus a synthetic check receipt is **not certification**; only a candidate for independent gate review. Existing app uses four persistent credential entry points, and changes must be tested under the same package identity and safe update path. Keep backup checks and migration validation separate from normal app builds until a canonical claim authorizes work.
