# Cantiere Image LOCAL ML Kit Flutter plugin

Functional Flutter/Android plugin adapted from Cantiere source at immutable
commit `acc8d28b54489c91cb4f59552a1be2e07203de1a`. The
native bridge uses Android's bundled on-device Google ML Kit image-labeling
artifact `com.google.mlkit:image-labeling:17.0.9`, not a Cloud VLM.

## API

```dart
final labels = await CantiereLocalImageVision().labelFile('/path/to/photo.jpg');
print(labels.text);
```

Call with a **local readable image path on Android**. The native plugin performs
file-size checking (8 MiB), low-memory checks, bounded decoding (1024-pixel edge,
RGB_565), one job at a time, and native label inference. Dart filters categories
below 0.55 confidence and reports at most five with honest limitations.

This is category tagging, not object counts, OCR, colors, a full visual
description, or conversational vision. No picture, prompt, or credential is
routed to a Cloud provider by this plugin.

For a *different* Flutter app, add this package as a path dependency and let
Flutter register `LocalImageVisionPlugin` automatically. **Do not install
alongside the original Cantiere MainActivity bridge without removing or
disabling its existing `LocalImageVisionBridge.register()` call:** both use
`com.aiorchestrator/local_image_vision` and would compete for one channel.

## Tests

```sh
flutter pub get
flutter analyze
flutter test
```

Android compilation validation is performed by the separate scoped Library
CI. A build or mocked MethodChannel test does not prove ML Kit inference on
a physical Galaxy S24 FE; that still requires a device test.

**Experimental/internal-only**. License, security and distribution review
pending. Native ML Kit and Android Gradle dependencies are subject to the
host app's SDK/minSdk constraints. No new APK is installed by this package.
