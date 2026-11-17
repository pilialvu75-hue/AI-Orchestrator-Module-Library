import 'package:aivexus_fixed_chunks/fixed_chunks.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <int>[1, 2, 3, 4, 5];
    final before = List<int>.from(d);
    if (chunkIntegers(d, 2).toString() != '[[1, 2], [3, 4], [5]]')
      throw StateError('partition');
    if (chunkIntegers(<int>[], 3).isNotEmpty) throw StateError('empty');
    if (chunkIntegers(<int>[-1, 0], 9).toString() != '[[-1, 0]]')
      throw StateError('large');
    if (d.toString() != before.toString()) throw StateError('mutated');
    var rejected = false;
    try {
      chunkIntegers(d, 0);
    } on ArgumentError {
      rejected = true;
    }
    if (!rejected) throw StateError('invalid size');
    print(
        'PASS: independent Dart consumer for original model-generated fixed_chunks');
  });
}
