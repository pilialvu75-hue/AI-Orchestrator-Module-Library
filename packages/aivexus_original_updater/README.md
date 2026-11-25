# AIVEXUS original updater — 0.1.0-dev.1

Experimental first-party extraction, **not a certified production module**. Source: [AI Orchestrator Riserva at 5d5a3905ceced2c01c8f1d4a8c44ac75d9215fe0](https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/tree/5d5a3905ceced2c01c8f1d4a8c44ac75d9215fe0/lib/core/system/update). All 17 original updater Dart files and 20 original test files are included; imports and configuration boundaries are adapted, not the update algorithms. Original fixture is included for regression tests only; do not use it as another app's live feed.

## Consumer integration

Use the Git dependency with `path: packages/aivexus_original_updater` and an exact reviewed commit SHA. Import `package:aivexus_original_updater/aivexus_original_updater.dart`. Instantiate the original UpdateChecker with your own manifestUrl, githubOwner, githubRepo, targetPlatform and desktop asset names; initialize preferences and comparator. Desktop hosts can use configurePlatformUpdateServices with their explicit endpoints and all three asset names. Android hosts instantiate UpdateManager with the checker and AndroidIntentHandler. Do not point VoiceBridge at Riserva's manifest or installer.

The module has no Beta Access registration requirement. The Android MethodChannel adapters are preserved, but the host must implement the original native background_downloads and android_intents channels (including verified APK handling, FileProvider and install confirmation). See [original MainActivity](https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/blob/5d5a3905ceced2c01c8f1d4a8c44ac75d9215fe0/android/app/src/main/kotlin/com/aiorchestrator/MainActivity.kt) and [BackgroundDownloads](https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/blob/5d5a3905ceced2c01c8f1d4a8c44ac75d9215fe0/android/app/src/main/kotlin/com/aiorchestrator/BackgroundDownloads.kt). Do not transplant unrelated MainActivity functionality. Original settings UI remains in [source](https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/blob/5d5a3905ceced2c01c8f1d4a8c44ac75d9215fe0/lib/features/settings/presentation/pages/modules/update_settings_page.dart); host UI adapter still required. No physical OTA or rollback validation claimed.

## Verification

From this directory: `flutter pub get`, `flutter analyze --no-fatal-infos --no-fatal-warnings`, `flutter test`. CI runs original regression tests. Development-only until CI, consumer integration, license/security and actual OTA evidence are available. See provenance.json for original blob hashes.
