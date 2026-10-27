# Cantiere offline image-label post-processing

A dependency-free Dart processing module adapted from the Cantiere Android
local image category classifier. The exact pinned native Android ML Kit bridge,
Dart host service, and Flutter tests are retained under `reference/`.

The **runnable Dart API processes labels**, not photographs. The Android native
bridge is present for provenance, not installed as a plugin.

Usage (after adding this package as a Dart dependency):

```dart
import 'package:cantiere_local_image_labels/local_image_labels.dart';
final summary = LocalImageLabelProcessor.fromNative([
  {'label': 'Apple', 'confidence': 0.92},
]);
print(summary.text);
```

Verification:

```sh
dart pub get --offline
dart analyze lib tool
dart run tool/self_test.dart
```

The real Cantiere MethodChannel is `com.aiorchestrator/local_image_vision`,
method `labelImage`, with the ML Kit image-labeling library 17.0.9. The host
must separately provide actual native inference, file size (8 MiB), RAM
budget, permissions, and timeout checks.

Source-only experimental package, *not* a full image recognizer, deployable
Flutter plugin, production release or proof on a Galaxy S24 FE.