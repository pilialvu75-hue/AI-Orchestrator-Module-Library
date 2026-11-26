import 'dart:math';
import '../../intake/utility.llm_generated.delta_codec/0.1.0/payload/src/lib/delta_codec.dart';

void equal(List<int> a, List<int> b, String label) {
  if (a.length != b.length) throw StateError('$label: length');
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) throw StateError('$label: index $i');
  }
}

void roundTrip(List<int> input, String label) {
  final original = List<int>.of(input);
  final encoded = encodeDeltas(input);
  final encodedCopy = List<int>.of(encoded);
  equal(decodeDeltas(encoded), original, label);
  equal(input, original, '$label input unchanged');
  equal(encoded, encodedCopy, '$label encoded unchanged');
}

void main() {
  equal(encodeDeltas([4200, 4202, 4205, 4204]), [4200, 2, 3, -1], 'known vector');
  equal(decodeDeltas([4200, 2, 3, -1]), [4200, 4202, 4205, 4204], 'known inverse');
  for (final input in <List<int>>[
    [], [0], [-1], [1, 1, 1], [0, -1, 0, 1],
    [2147483647, -2147483648, 0],
    [9223372036854775807, -9223372036854775807 - 1, 0],
    List<int>.generate(100000, (i) => i % 2 == 0 ? i : -i),
  ]) {
    roundTrip(input, 'edge case length ${input.length}');
  }
  final random = Random(20261126);
  for (var n = 0; n < 1000; n++) {
    roundTrip(List.generate(random.nextInt(512), (_) => random.nextInt(2000000000) - 1000000000), 'random $n');
  }
  final data = List<int>.generate(1000000, (i) => 4200 + i % 10);
  final watch = Stopwatch()..start();
  final encoded = encodeDeltas(data);
  final encodeUs = watch.elapsedMicroseconds;
  watch.reset();
  equal(decodeDeltas(encoded), data, 'large round trip');
  print('PASS: deterministic edge cases, 1000 random vectors, large round trip');
  print('Encode microseconds: $encodeUs; decode plus verification microseconds: ${watch.elapsedMicroseconds}');
  print('Element count original=${data.length}, encoded=${encoded.length}; no binary compression claimed.');
}
