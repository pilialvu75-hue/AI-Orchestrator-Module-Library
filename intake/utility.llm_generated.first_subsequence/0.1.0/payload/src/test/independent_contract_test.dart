import 'package:aivexus_first_subsequence/first_subsequence.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    if (findSubsequence(<int>[2, 3, 2, 3, 4], <int>[2, 3, 4]) != 2)
      throw StateError('first match');
    if (findSubsequence(<int>[1, 2, 1, 2], <int>[1, 2]) != 0)
      throw StateError('earliest');
    if (findSubsequence(<int>[1, 2], <int>[3]) != -1)
      throw StateError('missing');
    if (findSubsequence(<int>[], <int>[]) != 0) throw StateError('empty');
    if (findSubsequence(<int>[1], <int>[1, 2]) != -1)
      throw StateError('too long');
    print(
        'PASS: independent Dart consumer for original model-generated first_subsequence');
  });
}
