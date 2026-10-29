# Aivexus external Dart logging — 0.1.1 experimental

Pinned **public** Dart `dart-lang/core` logging 1.3.0 (commit `8151b9f57fa3fee10421a19ce24470e143c0dee5`) with all 13 original Git blobs, original BSD-3-Clause license, and separately maintained local Aivexus Dart adapter.

## Closed diagnostic vocabulary
The adapter's `emit(AivexusEventCode, severity: ...)` accepts only enum constants. It does **not** accept arbitrary user strings, paths, prompt text or dynamic event labels. An event-code addition requires a new reviewed module version. It uses a detached upstream Logger, a bounded memory-only buffer and no persistence or network transport.

## Try in isolation
```sh
cd intake/diagnostics.logging.dartlang.logging_adapter/0.1.1/payload/src
dart pub get --offline
dart analyze lib
dart analyze tool
dart run tool/self_test.dart
```

**NOT CERTIFIED.** The module is an experimental candidate, not an installed AI-Orchestrator feature. Independent privacy, license, dependency review and platform-specific runtime integration remain necessary. The original v0.1.0 source and test evidence remain unchanged.
