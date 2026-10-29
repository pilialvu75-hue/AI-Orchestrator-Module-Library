# Aivexus external logging — runnable source package, not certified

This is a **real, local Dart adapter** for the public upstream [dart-lang/core logging](https://github.com/dart-lang/core/tree/8151b9f57fa3fee10421a19ce24470e143c0dee5/pkgs/logging) package, version 1.3.0. Vendored sources are byte-identical to the pinned Git tree, including the BSD-3-Clause LICENSE and AUTHORS. No code from private repositories is included.

Use on a machine with Dart >=3.4:

```sh
cd sandbox/external_dart_logging
dart pub get --offline
dart analyze
dart run tool/self_test.dart
```

The logger is detached from the global logger, does not intercept stdout, and stores only bounded event codes and severity in memory. It does not store raw prompts or messages, paths or tokens; no network or persistence is implemented. This does **not** establish Android/Windows/macOS/iOS runtime compatibility or complete privacy compliance. The source and adapter need independent review and target-specific validation before production/certification.

**State**: experimental, source materialized, executable self-test; **NOT CERTIFIED**. The three historical source-less certified catalog entries remain preserved and excluded from usable resolver results. No claim is made that this new sandbox is certified or currently installed in AI-Orchestrator.
