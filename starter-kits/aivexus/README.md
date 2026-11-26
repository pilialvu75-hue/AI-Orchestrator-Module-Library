# AIVEXUS Starter Pack — 0.1.0 (draft)

A clean Flutter application scaffold, independent of the Module Library runtime. The clean cross-platform scaffold includes no modules. The approved Android profile adds only the original updater. No Beta Access, Diagnostics or AI engine. No networking, analytics, secrets or permissions are added by this template.

Generate a new project into a nonexistent directory, with Flutter 3.35.7 stable (pinned CI baseline) and Python 3 installed:

```powershell
python generate.py --name rendezvous_demo --display-name "AIVEXUS RendezVous Demo" --out ./rendezvous_demo
cd rendezvous_demo
flutter pub get
flutter test
flutter run
```

The generator uses the official Flutter scaffold with `com.aivexus` organization, app-specific project slug, initial version 0.1.0+1, and Android/Windows/Linux/macOS targets. It adds an app shell with system light/dark theme and French, Italian, English and Spanish labels. Operating-system launcher names, icons, signing identities and packaging need per-product configuration before release. Platform availability depends on the Flutter SDK and native toolchain installed on the host; Windows 7/8.1 and real device compatibility are not claimed.

Keep the generated project in its own repository. Add future modules explicitly only when requested, after standalone tests. Never share credentials across apps. The starter does not contain customer data or network endpoints. No automatic update logic is present in the clean profile. The approved Android profile includes automatic OTA checks.

CI pins Flutter 3.35.7 to avoid unreviewed SDK API changes; new SDK versions must be tested before updating this baseline. CI generates fresh projects, resolves only Flutter SDK dependencies, runs static analysis and widget tests and attempts native builds for Android/Windows/Linux/macOS. The starter is not considered release-ready until target builds pass.

## Approved Android updater profile (issue #401)

New Android apps should use the explicit Android profile; a real app must supply its own owner and repository. Example:

```powershell
python generate.py --name my_app --display-name "AIVEXUS My App" --out ./my_app --android-updater --github-owner YOUR_OWNER --github-repo YOUR_REPO
```

Run from a Library checkout containing pinned commit 5f0b3093c15177dff850a914fcfe52ac7e2fc70a. The generator exports only that updater package into vendor/, copies the owner-approved RendezVous notice UI and native install/download bridge, and adds a local dependency. The generated app is Android-only; the other platforms retain the clean scaffold until physical OTA validation. The feed and APK downloads must belong to the configured public GitHub repository. No embedded credentials. The signing workflow remains opt-in; provision the owner's permanent key and configure signing/README.md before release.

Customer profile starts stable with selector hidden. Tester profile (--tester) keeps the selector; use a separate application ID for tester builds to avoid migrating pending prerelease APKs into customer builds. An in-place tester-to-customer migration is not yet supported. Approved French updater labels preserved; four-language translation and commercial migration tests remain pending. This is a new integration of the approved functionality with dev.3 strict checksum/manifest options; it needs consumer CI and physical tests. No global certification.
