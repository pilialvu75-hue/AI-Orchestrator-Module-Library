import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:ai_orchestrator/core/orchestrator/state_engine/chat_attachment.dart';
import 'package:ai_orchestrator/core/runtime/inference/chat_turn.dart';
import 'package:ai_orchestrator/features/chat/data/services/chat_image_vision_service.dart';

/// The first offline image capability: device-side category labels, NOT a
/// general-purpose VLM. Never claim colors, counts, OCR, or details not proven
/// by the labels. Future mtmd/vision GGUF support will use a separate backend.
final class AndroidChatLocalImageVisionService implements ChatImageVisionService {
  AndroidChatLocalImageVisionService({
    MethodChannel? channel,
    bool? supportedPlatform,
  })  : _channel =
            channel ?? const MethodChannel('com.aiorchestrator/local_image_vision'),
        _supportedPlatform = supportedPlatform ??
            (!kIsWeb && defaultTargetPlatform == TargetPlatform.android);

  static const int maxImageBytes = 8 * 1024 * 1024;
  static const Duration requestTimeout = Duration(seconds: 20);
  final MethodChannel _channel;
  final bool _supportedPlatform;

  @override
  Future<ChatImageVisionResult> analyze({
    required String providerId,
    required ChatAttachment image,
    required String prompt,
    String? systemPrompt,
    List<ChatTurn> context = const <ChatTurn>[],
  }) async {
    if (providerId != 'local') {
      throw StateError('Il riconoscimento visivo locale non usa provider Cloud.');
    }
    if (!_supportedPlatform) {
      throw UnsupportedError(
        'Il riconoscimento Image offline non è ancora supportato su questa '
        'piattaforma. Non è stata inviata alcuna immagine al Cloud.',
      );
    }
    if (!image.isImage ||
        image.uploadState != ChatAttachmentUploadState.ready ||
        image.path.trim().isEmpty) {
      throw StateError('Immagine non disponibile o ancora in preparazione.');
    }
    final file = File(image.path);
    if (!await file.exists()) {
      throw StateError('Immagine originale non trovata: selezionala di nuovo.');
    }
    final fileSize = await file.length();
    if (fileSize <= 0 || fileSize > maxImageBytes) {
      throw StateError('Image LOCAL accetta immagini fino a 8 MB.');
    }
    // No raw image, user prompt, user context or secrets ever enter diagnostics.
    final result = await _channel
        .invokeMethod<List<dynamic>>('labelImage', <String, Object>{
          'path': file.path,
        })
        .timeout(requestTimeout, onTimeout: () {
          throw StateError(
            'Image LOCAL: riconoscimento troppo lento. Riprova con una foto '
            'più piccola; nessuna immagine è stata inviata al Cloud.',
          );
        });
    final labels = <_LocalImageLabel>[];
    for (final item in result ?? const <dynamic>[]) {
      if (item is! Map) continue;
      final rawName = item['label'];
      final rawConfidence = item['confidence'];
      if (rawName is! String || rawConfidence is! num) continue;
      final name = rawName.trim().replaceAll(RegExp(r'\s+'), ' ');
      final confidence = rawConfidence.toDouble();
      if (name.isEmpty || name.length > 70 ||
          !confidence.isFinite || confidence < 0.55 || confidence > 1) {
        continue;
      }
      labels.add(_LocalImageLabel(name, confidence));
    }
    labels.sort((a, b) => b.confidence.compareTo(a.confidence));
    if (labels.isEmpty) {
      return const ChatImageVisionResult(
        providerId: 'localImageLabels',
        text: 'Non ho riconosciuto categorie visive con sufficiente '
            'affidabilità in questa foto. Il riconoscitore offline attuale '
            'è limitato; non posso descrivere dettagli, colori o testo '
            'dell\'immagine. Nessun dato è stato inviato al Cloud.',
      );
    }
    final detected = labels.take(5).map(
      (label) => '${label.name} (${(label.confidence * 100).round()}%)',
    );
    return ChatImageVisionResult(
      providerId: 'localImageLabels',
      text: 'Riconoscimento visivo sul dispositivo (categorie probabili): '
          '${detected.join(', ')}.\n'
          'Queste sono etichette stimate da un classificatore offline, '
          'non una descrizione completa. Non posso ancora dedurre con '
          'affidabilità colori, quantità, testo o altri dettagli della foto. '
          'Nessuna immagine è stata inviata al Cloud.',
    );
  }
}

final class _LocalImageLabel {
  const _LocalImageLabel(this.name, this.confidence);
  final String name;
  final double confidence;
}
