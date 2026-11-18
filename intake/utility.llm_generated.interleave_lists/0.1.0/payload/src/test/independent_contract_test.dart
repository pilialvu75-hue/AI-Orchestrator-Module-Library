import 'package:aivexus_interleave_lists/interleave_lists.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final l = <int>[1, 2, 3], r = <int>[-1, -2];
    if (interleaveIntegers(l, r).toString() != '[1, -1, 2, -2, 3]')
      throw StateError('interleave');
    if (interleaveIntegers(<int>[], <int>[4, 5]).toString() != '[4, 5]')
      throw StateError('left empty');
    if (interleaveIntegers(<int>[], <int>[]).isNotEmpty)
      throw StateError('both empty');
    if (l.toString() != '[1, 2, 3]' || r.toString() != '[-1, -2]')
      throw StateError('mutation');
    print(
        'PASS: independent Dart consumer for original model-generated interleave_lists');
  });
}
