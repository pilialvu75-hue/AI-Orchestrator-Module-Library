import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'src/local_image_labels.dart';

export 'src/local_image_labels.dart';

/// Android ML Kit offline image category classification, not a multimodal LLM.
///
/// The native plugin limits file size to 8 MiB, checks memory and downscales
/// bitmaps. This wrapper never sends the picture, prompt or context to Cloud.
class CantiereLocalImageVision {
  CantiereLocalImageVision({
    MethodChannel? channel,
    bool? supportedPlatform,
  })  : _channel = channel ??
            const MethodChannel('com.aiorchestrator/local_image_vision'),
        _supportedPlatform = supportedPlatform ??
            (!kIsWeb && defaultTargetPlatform == TargetPlatform.android);

  static const Duration timeout = Duration(seconds: 20);
  final MethodChannel _channel;
  final bool _supportedPlatform;

  Future<LocalImageLabelResult> labelFile(String imagePath) async {
    if (!_supportedPlatform) {
      throw UnsupportedError(
        'Image LOCAL ML Kit richiede Android. Nessuna immagine inviata al Cloud.',
      );
    }
    if (imagePath.trim().isEmpty) {
      throw ArgumentError.value(imagePath, 'imagePath', 'Missing local image');
    }
    final response = await _channel.invokeMethod<List<dynamic>>(
      'labelImage',
      <String, String>{'path': imagePath},
    ).timeout(timeout);
    return LocalImageLabelProcessor.fromNative(response ?? <Object?>[]);
  }
}
