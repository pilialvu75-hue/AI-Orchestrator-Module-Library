import 'package:aivexus_cumulative_max/cumulative_max.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <int>[-5, -8, 2, 1, 7, 7];
    if (cumulativeMaximum(d).toString() != '[-5, -5, 2, 2, 7, 7]')
      throw StateError('prefix maximum');
    if (cumulativeMaximum(<int>[]).isNotEmpty) throw StateError('empty');
    if (d.toString() != '[-5, -8, 2, 1, 7, 7]') throw StateError('input');
    print(
        'PASS: independent Dart consumer for original model-generated cumulative_max');
  });
}
