import 'package:aivexus_adjacent_pairs/adjacent_pairs.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    if (adjacentPairs(<int>[3, -1, 0, 0]).toString() !=
        '[[3, -1], [-1, 0], [0, 0]]') throw StateError('pairs');
    if (adjacentPairs(<int>[]).isNotEmpty) throw StateError('empty');
    if (adjacentPairs(<int>[5]).isNotEmpty) throw StateError('singleton');
    print(
        'PASS: independent Dart consumer for original model-generated adjacent_pairs');
  });
}
