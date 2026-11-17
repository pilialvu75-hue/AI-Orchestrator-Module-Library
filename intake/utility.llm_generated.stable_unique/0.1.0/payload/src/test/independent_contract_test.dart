import 'package:aivexus_stable_unique/stable_unique.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final original = <int>[3, 3, -1, 3, 2, -1, 0, 2, 0];
    final before = List<int>.from(original);
    final result = uniqueStable(original);
    if (result.toString() != '[3, -1, 2, 0]')
      throw StateError('stable distinct order failed: $result');
    if (original.toString() != before.toString())
      throw StateError('input mutated');
    if (identical(result, original))
      throw StateError('result is not a new list');
    if (uniqueStable(<int>[]).isNotEmpty)
      throw StateError('empty input failed');
    if (uniqueStable(<int>[5, 5, 5]).toString() != '[5]')
      throw StateError('duplicate removal failed');
    if (uniqueStable(<int>[-2, 7, -2, 7, 1]).toString() != '[-2, 7, 1]')
      throw StateError('negative number order failed');
    print('PASS: independent consumer of Qwen-generated stable-unique module');
  });
}
