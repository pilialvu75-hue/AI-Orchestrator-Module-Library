import 'package:aivexus_intersection_unique/intersection_unique.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final first = <int>[3, -1, 3, 2, 0, 2], second = <int>[2, 3, 2, 9];
    if (intersectStable(first, second).toString() != '[3, 2]')
      throw StateError('intersection');
    if (intersectStable(<int>[], second).isNotEmpty) throw StateError('empty');
    if (intersectStable(<int>[-5, -5, 0], <int>[-5]).toString() != '[-5]')
      throw StateError('duplicates');
    if (first.length != 6) throw StateError('mutation');
    print(
        'PASS: independent Dart consumer for original model-generated intersection_unique');
  });
}
