import 'package:aivexus_count_in_range/count_in_range.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <int>[-4, -1, 0, 2, 2, 9];
    if (countInRange(d, -1, 2) != 4) throw StateError('range');
    if (countInRange(d, 3, 3) != 0) throw StateError('none');
    if (countInRange(d, 10, -10) != 0) throw StateError('reverse');
    if (countInRange(<int>[], 0, 3) != 0) throw StateError('empty');
    if (d.length != 6) throw StateError('mutated');
    print(
        'PASS: independent Dart consumer for original model-generated count_in_range');
  });
}
