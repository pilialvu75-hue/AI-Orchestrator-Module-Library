# AIVEXUS Original Diagnostics 0.1.0-dev.3

Second proposed Starter Pack component, approved for development by the owner. Extracted from Riserva commit 67ae2cc352e6d54ec5cbbe7917958ad6e9e8ce28. Original event buffer, persistent crash-log sink, telemetry privacy policy and associated original tests retained with package import changes.

## Local-first recommended API

Import package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart. Await AivexusDiagnostics.instance.initialize() at application startup, optionally attachFlutterErrorCapture() (retain and call the returned detach callback at teardown), then record typed DiagnosticComponent and DiagnosticEvent values. No arbitrary user strings, errors, paths or credentials are accepted by the recommended event facade. The original raw RuntimeEventLog.emit is retained for source equivalence but is an internal API: do not route arbitrary user content or exception text into it. The sink keeps the latest crash history on disk with the original size cap. The test checks recovery by reopening the same storage; actual process-kill recovery is a separate physical test.

No backend, token, analytics SDK, updater or Beta Access dependency. The original telemetry bridge and abstract interface are retained for isolated policy tests, not enabled by default. No data is transmitted. A future consent-gated adapter needs a closed payload vocabulary, bounded queue, explicit endpoint and independent validation. Never transmit raw logs.

## Remaining work before Starter Pack integration

- Extract original resource monitor and native platform adapters; measure actual available metrics, report unsupported values as unavailable.
- Extract/adapt the hidden console (seven-click entry), crash diagnostics and user-facing privacy controls.
- Add standalone export, independent consumer tests, device restart/crash verification and authorization by the owner. Do not claim full physical crash capture or certification.
- Add automatic Flutter/platform error capture with documented host ownership and safe chaining; the initial facade only provides the optional Flutter error hook.
- Review storage privacy, retention and licensing. No application repository or existing updater behavior is changed.

Run flutter pub get, flutter analyze --no-fatal-infos --no-fatal-warnings, flutter test from this package.

## Resource telemetry extraction
Original Dart ResourceMonitor and original regression suite, with Android ResourceTelemetry.kt and isolated Windows resource channel. ResourceDiagnostics facade disables raw resource log persistence and samples only while a visible owner retains it; explicit sample() is available. Android reports available/total RAM, RSS, native heap, battery temperature proxy and pressure; Windows reports RAM, working set and CPU after a valid second sample. Missing GPU, disk, CPU or thermal readings are not estimated. macOS/Linux native metrics are not yet supported. Native sources require host registration and separate build/physical testing. For Android replace __ANDROID_NAMESPACE__, instantiate ResourceTelemetry(context, engine) when configuring the engine and call close() during cleanup. For Windows include resource_telemetry.h and call RegisterAivexusResourceTelemetry(engine->messenger()) after plugin registration. No network transport.

## Hidden console and automatic capture
After initialize(), call attachAutomaticErrorCapture() once; it chains FlutterError and root PlatformDispatcher handlers without suppressing original error behavior or recording exception text. Keep the detach callback. Wrap a non-interactive label in HiddenDiagnosticsEntry(child: ...). Seven taps within five seconds open the original adapted console, no visible menu button. This is not authentication. The console and copy/history features only present strict typed events, no GitHub upload. Local raw internal logger still exists for original regression equivalence and must not be exposed or used with user data. Clearing history requires confirmation. Labels are currently English; localization remains pending. Resources are shown in a foreground panel and polling stops on dispose/background. Native readings require host adapters. Isolate-specific errors and native crash detection require additional host evidence; retained markers are not proof of crash cause.
