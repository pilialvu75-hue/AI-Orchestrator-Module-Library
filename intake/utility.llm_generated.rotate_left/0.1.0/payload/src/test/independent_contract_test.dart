import 'package:aivexus_rotate_left/rotate_left.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <int>[1, 2, 3, 4];
    if (rotateLeft(d, 1).toString() != '[2, 3, 4, 1]') throw StateError('left');
    if (rotateLeft(d, 5).toString() != '[2, 3, 4, 1]') throw StateError('wrap');
    if (rotateLeft(d, -1).toString() != '[4, 1, 2, 3]')
      throw StateError('right');
    if (rotateLeft(<int>[], 3).isNotEmpty) throw StateError('empty');
    if (d.toString() != '[1, 2, 3, 4]') throw StateError('mutated');
    print(
        'PASS: independent Dart consumer for original model-generated rotate_left');
  });
}
