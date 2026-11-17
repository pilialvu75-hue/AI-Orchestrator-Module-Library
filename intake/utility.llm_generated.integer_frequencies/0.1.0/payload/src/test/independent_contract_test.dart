import 'package:aivexus_integer_frequencies/integer_frequencies.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final data = <int>[3, -1, 3, 0, -1, 3];
    final before = List<int>.from(data);
    final r = countFrequencies(data);
    if (r.length != 3 || r[3] != 3 || r[-1] != 2 || r[0] != 1)
      throw StateError('counts $r');
    if (r.keys.toList().toString() != '[3, -1, 0]')
      throw StateError('order $r');
    if (data.toString() != before.toString()) throw StateError('mutated');
    if (countFrequencies(<int>[]).isNotEmpty) throw StateError('empty');
    print(
        'PASS: independent Dart consumer for original model-generated integer_frequencies');
  });
}
