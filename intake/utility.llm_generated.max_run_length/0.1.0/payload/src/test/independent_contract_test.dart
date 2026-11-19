import 'package:aivexus_max_run_length/max_run_length.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    if (longestRunLength(<int>[1, 1, 2, 2, 2, 3, 3]) != 3)
      throw StateError('longest');
    if (longestRunLength(<int>[]) != 0) throw StateError('empty');
    if (longestRunLength(<int>[-1, -1, -1, -1]) != 4)
      throw StateError('all same');
    if (longestRunLength(<int>[4, 5, 6]) != 1) throw StateError('distinct');
    print(
        'PASS: independent Dart consumer for original model-generated max_run_length');
  });
}
