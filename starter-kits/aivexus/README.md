# AIVEXUS Starter Pack — 0.1.0 (draft)

A clean Flutter application scaffold, independent of the Module Library runtime. **No updater, Beta Access, Diagnostics, AI engine, or other AIVEXUS module is included.** No networking, analytics, secrets or permissions are added by this template.

Generate a new project into a nonexistent directory, with Flutter stable and Python 3 installed:

```powershell
python generate.py --name rendezvous_demo --display-name "AIVEXUS RendezVous Demo" --out ./rendezvous_demo
cd rendezvous_demo
flutter pub get
flutter test
flutter run
```

The generator uses the official Flutter scaffold with `com.aivexus` organization, app-specific project slug, initial version 0.1.0+1, and Android/Windows/Linux/macOS targets. It adds an app shell with system light/dark theme and French, Italian, English and Spanish labels. Operating-system launcher names, icons, signing identities and packaging need per-product configuration before release. Platform availability depends on the Flutter SDK and native toolchain installed on the host; Windows 7/8.1 and real device compatibility are not claimed.

Keep the generated project in its own repository. Add future modules explicitly only when requested, after standalone tests. Never share credentials across apps. The starter does not contain customer data or network endpoints. No automatic update logic is present.

CI generates fresh projects, resolves only Flutter SDK dependencies, runs static analysis and widget tests and attempts native builds for Android/Windows/Linux/macOS. The starter is not considered release-ready until target builds pass.
