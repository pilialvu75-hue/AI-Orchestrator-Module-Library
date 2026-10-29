# External Dart logging — downstream consumption proof

This is a separate **pure-Dart consumer project**, not the Library module itself.
Its dependency is a local path to the real, source-pinned, `tested` Library
candidate at `intake/diagnostics.logging.dartlang.logging_adapter/0.1.0/payload/src`.
No package registry or network permission is needed for resolution.

```sh
cd examples/external_logging_consumer
dart pub get --offline
dart analyze
dart run bin/main.dart
```

Expected: `PASS: separately resolved external Library module provides real structured events`.

This proves the tested module's public Dart API can be imported and used as a
separate app dependency on the Linux CI host. **Not certified**: it is not a
production release, not installed in AI-Orchestrator, and Android/Windows/macOS
compatibility, privacy/security audit and license verification are not yet
proven. The application must obtain approval before deployment.
