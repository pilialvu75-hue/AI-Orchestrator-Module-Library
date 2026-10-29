# Downstream consumer of the **tested** typed external logging module

```sh
cd examples/external_logging_typed_consumer
dart pub get --offline
dart analyze
dart run bin/main.dart
```

This consumer depends directly on the materialized public-source Library
candidate at `intake/diagnostics.logging.dartlang.logging_adapter/0.1.1`
rather than a copy or metadata reference. It tests the closed enum event
vocabulary and rejects free-text injection at runtime.

**Not certified or installed in AI-Orchestrator.** Linux Dart is the only
verified host; independent license/security/privacy approval and further
host-platform tests are required.
