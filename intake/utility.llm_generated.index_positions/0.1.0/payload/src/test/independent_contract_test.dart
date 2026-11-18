import 'package:aivexus_index_positions/index_positions.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <int>[4, 9, 4, 4, 9];
    final r = groupIndices(d);
    if (r.keys.toList().toString() != '[4, 9]') throw StateError('key order');
    if (r[4].toString() != '[0, 2, 3]' || r[9].toString() != '[1, 4]')
      throw StateError('positions');
    if (groupIndices(<int>[]).isNotEmpty) throw StateError('empty');
    if (d.toString() != '[4, 9, 4, 4, 9]') throw StateError('mutated');
    print(
        'PASS: independent Dart consumer for original model-generated index_positions');
  });
}
