import 'package:aivexus_palindrome_filter/palindrome_filter.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <String>['aba', 'abc', 'Aba', '', 'aa', 'aba', 'z'];
    final r = filterPalindromes(d);
    if (r.toString() != '[aba, , aa, aba, z]') throw StateError('filter: $r');
    if (filterPalindromes(<String>[]).isNotEmpty)
      throw StateError('empty input');
    if (d.length != 7) throw StateError('mutation');
    print(
        'PASS: independent Dart consumer for original model-generated palindrome_filter');
  });
}
