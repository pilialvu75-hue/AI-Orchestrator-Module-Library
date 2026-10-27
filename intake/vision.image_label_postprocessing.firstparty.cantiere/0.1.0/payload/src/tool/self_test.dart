import '../lib/local_image_labels.dart';

int passed = 0;
void check(bool condition, String name) {
  if (!condition) throw StateError('FAIL: $name');
  passed++;
}

void main() {
  final result = LocalImageLabelProcessor.fromNative(<Object?>[
    <String, Object?>{'label': ' Fruit  Bowl ', 'confidence': 0.74},
    <String, Object?>{'label': 'Apple', 'confidence': 0.92},
    <String, Object?>{'label': 'Guess', 'confidence': 0.15},
  ]);
  check(LocalImageLabelResult.providerId == 'localImageLabels', 'local origin');
  check(result.hasCategories, 'categories recognized');
  check(result.labels.length == 2, 'below threshold excluded');
  check(result.labels.first.name == 'Apple', 'descending confidence');
  check(result.labels.last.name == 'Fruit Bowl', 'whitespace normalized');
  check(result.text.contains('Apple (92%)'), 'rounded confidence');
  check(!result.text.contains('Guess'), 'low confidence excluded');
  check(result.text.contains('non una descrizione completa'), 'limits disclosed');
  check(result.text.contains('Nessuna immagine è stata inviata al Cloud'),
      'offline result does not imply Cloud transfer');

  final empty = LocalImageLabelProcessor.fromNative(<Object?>[
    null,
    123,
    {'label': '', 'confidence': 0.9},
    {'label': 'Unknown', 'confidence': double.nan},
    {'label': 'Unknown', 'confidence': double.infinity},
    {'label': 'Unknown', 'confidence': -0.2},
    {'label': 'Unknown', 'confidence': 1.01},
    {'label': 'Unknown', 'confidence': '0.9'},
    {'label': List<String>.filled(71, 'Z').join(), 'confidence': 1},
  ]);
  check(!empty.hasCategories, 'invalid inputs all rejected');
  check(empty.text.contains('Non ho riconosciuto categorie'), 'honest fallback');

  final top = LocalImageLabelProcessor.fromNative(
    List<Object?>.generate(
      12, (i) => {'label': 'Label$i', 'confidence': 0.99 - i * 0.01}),
  );
  check(top.labels.length == LocalImageLabelProcessor.maxLabels,
      'bounded top-five');
  check(top.labels.first.name == 'Label0', 'highest rank');
  check(top.labels.last.name == 'Label4', 'fifth rank');
  check(top.text.contains('Label0') && !top.text.contains('Label5'),
      'sixth category omitted');
  final boundary = LocalImageLabelProcessor.fromNative(<Object?>[
    {'label': 'Exactly', 'confidence': 0.55},
    {'label': 'JustBelow', 'confidence': 0.549},
  ]);
  check(boundary.labels.length == 1 &&
      boundary.labels.single.name == 'Exactly', 'threshold inclusive');
  check(boundary.labels.single.confidence == 0.55, 'confidence retained');
  try {
    result.labels.add(const LocalImageLabel('mutated', 1));
    throw StateError('FAIL: result should be immutable');
  } on UnsupportedError {
    passed++;
  }
  print('PASS: $passed Dart offline image-label checks');
}
