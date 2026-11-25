# Android permanent signing — issue #401

Each application ID needs a persistent owner-controlled release key, not the disposable CI debug key. Separate application IDs (e.g. beta vs stable) may have separate keys. For an existing application, restore its existing key; never silently create another one.

## Owner setup (one-time, local, not CI)

Use a trusted computer with the JDK installed. In a private directory outside Git, run:

    keytool -genkeypair -keystore app-release.p12 -storetype PKCS12 -alias release -keyalg RSA -keysize 3072 -validity 10000

Enter the password at the prompt. Export the public certificate fingerprint with:

    keytool -list -v -keystore app-release.p12 -alias release

Record the SHA-256 fingerprint in the app's public release configuration. Keep two encrypted backups of the keystore and a separately protected password; test restoration locally. Do not send the private key or password via chat or commit them. For CI, use the application's protected GitHub release environment secrets: ANDROID_KEYSTORE_B64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD. PKCS12 generally uses the same store and key password. Use protected release environment and trusted branches only. PR builds remain unsigned/debug and have no signing secrets. Do not use pull_request_target to execute PR code with secrets.

`verify_apk.py` checks an already signed APK against explicit app ID, versionCode, last published versionCode and owner-approved certificate. It computes SHA-256 of the final bytes and writes a receipt only after all checks pass. For a first release, pass previous version code 0; otherwise read the authoritative published manifest, not a guessed number. This tool does not create a private key, sign, publish, or alter an APK.

Release sequence: build a release APK; sign with the protected persistent keystore (Android SDK apksigner); verify with the gate; upload immutable asset; download the published asset and compare its bytes to receipt; publish manifest last, with apk_sha256 and apk_size_bytes. Reject any failure. Never expose keystores via artifact or logs. Require owner-approved signing environment before publication. The initial implementation contains the local verification gate and fixture tests; release workflow, actual protected key provisioning and two successive physical OTA tests remain outstanding.

The starter pack does not include the updater or any other Library module yet. References: #401, #377.

## Optional release workflow (public GitHub feed only)

Copy `verify_apk.py`, `release_gate.py` and `release-config.example.json` into the consumer repository `signing/` directory. Rename the example to `release-config.json` and replace the package ID and fingerprint. Create a reviewed `update/version.json` baseline containing `version`, `versionCode` (0 only for an entirely new app) and `min_supported`. Create protected `android-release` and `android-publication` environments restricted to main, with required owner approval and the four secrets in `android-release` only. Copy `android-release.yml.template` to `.github/workflows/android-release.yml` explicitly. Manual dispatch only. The workflow checks the prior manifest, builds and tests, signs with the persistent key, verifies the APK, then publishes an immutable versioned asset and downloads it without authentication to verify its digest before updating the manifest using the previous blob SHA. Public release visibility is deliberate: do not enable for private apps or reserved code. A failed publication can leave a release without a manifest update; inspect and recover manually rather than overwrite assets. This template has not yet been exercised with a real protected key. No updater dependency is installed.
