# Privacy-safe structured diagnostics (pure Dart)

This locally authored candidate contains executable Dart source, not an
upstream pointer. It implements a conservative, vocabulary-only adapter to
the draft diagnostics.logging.v1 logical contract.

No free-form message, prompt, model path, user ID, authorization header or
arbitrary string value is accepted. Unknown fields and invalid values are
discarded before any event representation can be exported.

Usage:
    final event = PrivacyDiagnosticEvent(
      eventCode: 'LOCAL_INFERENCE',
      severity: 'info',
      timestamp: DateTime.now(),
      fields: {'stage': 'decode', 'duration_ms': 500},
    );
    final safe = event.toMap();

Run (Dart SDK only, no package dependencies):
    dart pub get
    dart analyze --fatal-infos
    dart run bin/self_test.dart

Evidence scope: GitHub Actions Ubuntu/Dart SDK static and functional checks.
No Android, iOS, GPU, runtime, transport or privacy certification is claimed.
The Library module lifecycle and independent security reviewer remain pending.
