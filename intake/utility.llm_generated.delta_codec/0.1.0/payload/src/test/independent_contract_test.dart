import 'package:aivexus_delta_codec/delta_codec.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final samples = <int>[12, -4, -4, 9, 0];
    final original = List<int>.from(samples);
    final encoded = encodeDeltas(samples);
    if (encoded.toString() != '[12, -16, 0, 13, -9]')
      throw StateError('encoding failed: $encoded');
    if (decodeDeltas(encoded).toString() != samples.toString())
      throw StateError('decoding failed');
    if (samples.toString() != original.toString())
      throw StateError('input mutated');
    if (encodeDeltas(<int>[]).isNotEmpty || decodeDeltas(<int>[]).isNotEmpty)
      throw StateError('empty input failed');
    print('PASS: independently consumed LLM-generated delta module');
  });
}
