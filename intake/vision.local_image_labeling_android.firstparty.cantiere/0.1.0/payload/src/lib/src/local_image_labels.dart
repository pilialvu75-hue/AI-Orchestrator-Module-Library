/// Pure Dart post-processing of offline Android image labels.
///
/// Extracted/adapted from the pinned Cantiere vision service. Image decoding,
/// ML Kit model inference, file limits and RAM checks remain the Android
/// host bridge's responsibility. No IO, telemetry, network or Cloud routing.
class LocalImageLabel {
  const LocalImageLabel(this.name, this.confidence);
  final String name;
  final double confidence;
}

class LocalImageLabelResult {
  const LocalImageLabelResult({required this.labels, required this.text});
  static const String providerId = 'localImageLabels';
  final List<LocalImageLabel> labels;
  final String text;
  bool get hasCategories => labels.isNotEmpty;
}

abstract final class LocalImageLabelProcessor {
  static const double minConfidence = 0.55;
  static const int maxLabels = 5;

  static LocalImageLabelResult fromNative(Iterable<Object?> rawLabels) {
    final labels = <LocalImageLabel>[];
    for (final item in rawLabels) {
      if (item is! Map) continue;
      final rawName = item['label'];
      final rawConfidence = item['confidence'];
      if (rawName is! String || rawConfidence is! num) continue;
      final name = rawName.trim().replaceAll(RegExp(r'\s+'), ' ');
      final confidence = rawConfidence.toDouble();
      if (name.isEmpty ||
          name.length > 70 ||
          !confidence.isFinite ||
          confidence < minConfidence ||
          confidence > 1) {
        continue;
      }
      labels.add(LocalImageLabel(name, confidence));
    }
    labels.sort((a, b) => b.confidence.compareTo(a.confidence));
    final selected = List<LocalImageLabel>.unmodifiable(labels.take(maxLabels));

    if (selected.isEmpty) {
      return const LocalImageLabelResult(
        labels: <LocalImageLabel>[],
        text: 'Non ho riconosciuto categorie visive con sufficiente '
            'affidabilità in questa foto. Il riconoscitore offline attuale '
            'è limitato; non posso descrivere dettagli, colori o testo '
            'dell\'immagine. Nessun dato è stato inviato al Cloud.',
      );
    }
    final detected = selected.map(
      (label) => '${label.name} (${(label.confidence * 100).round()}%)',
    );
    return LocalImageLabelResult(
      labels: selected,
      text: 'Riconoscimento visivo sul dispositivo (categorie probabili): '
          '${detected.join(', ')}.\n'
          'Queste sono etichette stimate da un classificatore offline, '
          'non una descrizione completa. Non posso ancora dedurre con '
          'affidabilità colori, quantità, testo o altri dettagli della foto. '
          'Nessuna immagine è stata inviata al Cloud.',
    );
  }
}
