# Android secure preferences backup exclusion — PROPOSAL ONLY

This directory is **NOT part of the Android application's source tree**.
Do not install, merge, or ship it from this draft intake PR. Android issue:
https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/issues/849

## Verified inputs

- Published APK: `v1.0.12+3204`, asset `643772718`, SHA-256 `551fa971087bbacf1848e8d17fb68599166a664a1cf0d60991038708a6b43073`.
- Read-only real manifest: https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library/actions/runs/39033084733 (`allowBackup`, `dataExtractionRules`, `fullBackupContent` all absent).
- The four current Dart secret consumers construct `FlutterSecureStorage()` without custom Android options, as observed on `Ai-orchestrator-riserva` main.
- Upstream `flutter_secure_storage` 11.2.0 pinned SHA `e8eeb449cd512b26153f0a3376dfe374dd39a999` uses default data prefs `FlutterSecureStorage`, wrapped-key prefs `FlutterSecureKeyStorage`, and namespaced plus legacy algorithm-config prefs `FlutterSecureStorageConfiguration:FlutterSecureStorage` / `FlutterSecureStorageConfiguration`.
- **Still confirm the exact file naming at the resolved 10.3.4 plugin package**, and enumerate files on a disposable installation before promotion. The 11.2.0 source does not prove that earlier builds have no other prefs or namespace conventions.

## Proposed Android integration for the authorized platform-android worker

After acquiring a **separate canonical Android claim**, and reviewing existing project XML resources, consider copying the two XML files into `android/app/src/main/res/xml/`. In the app's existing `<application>` tag, *propose* adding:

```xml
android:fullBackupContent="@xml/backup_rules"
android:dataExtractionRules="@xml/data_extraction_rules"
```

The two XML files contain *only exclude rules*, so they aim to preserve the platform's default backup behavior for unrelated application settings while excluding specific Keystore-bound preferences. The `<cloud-backup>` and `<device-transfer>` branches have identical exclusions: Android 12+ D2D is distinct from cloud backup. Android 11 and earlier use `full-backup-content`. No blanket `allowBackup=false` is proposed.

These are **initial file names, not an exhaustive future-proof security policy**. If another plugin version, namespace, backup domain or application-specific token location is found, stop and expand the inventory/review first. Extra device-protected SharedPreferences or future cross-platform transfer pathways must also be assessed. Use neither glob patterns nor a broad `<exclude domain="sharedpref" path="."/>` without reviewing the loss of ordinary backed-up settings.

## Required proof after Android change

1. Compile an APK from an exact reviewed head with preserved signing/update lineage; verify hash/identity and dump its **merged** `AndroidManifest.xml`.
2. Check that its two resource references point to the compiled correct XML files; inspect the **compiled XML resource content**, not just the existence of reference attributes.
3. Verify explicit exclusions for all four pref files in legacy, cloud and D2D policies. Confirm ordinary non-sensitive preferences are still backed up. Confirm no unintended change to app data persistence.
4. On a disposable fixture installation, seed fake values under the old `flutter_secure_storage` version, verify restore against the backup boundaries and Keystore, then check `checkUpgradeStatus()` before the first read after a candidate upgrade. Stop on ambiguous/destructive results.
5. Collect pass/fail proof without transmitting any credential value, token hash, raw app data or Keystore data. Physical S24 FE proof is separate from passing GitHub CI.
6. Independent review and canonical approval are required before merge/release; this template itself is not evidence of restored-secret retention or a certified Library module.

Sources:
- https://developer.android.com/about/versions/12/behavior-changes-12#backup-restore
- https://developer.android.com/identity/data/autobackup
- https://github.com/juliansteenbakker/flutter_secure_storage/blob/e8eeb449cd512b26153f0a3376dfe374dd39a999/flutter_secure_storage/android/src/main/java/com/it_nomads/fluttersecurestorage/FlutterSecureStorageConfig.java
- https://github.com/juliansteenbakker/flutter_secure_storage/blob/e8eeb449cd512b26153f0a3376dfe374dd39a999/flutter_secure_storage/android/src/main/java/com/it_nomads/fluttersecurestorage/NamespacedConfigSource.java
