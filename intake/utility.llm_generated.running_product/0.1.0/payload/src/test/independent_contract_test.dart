import 'package:aivexus_running_product/running_product.dart';
import 'package:test/test.dart';

void main() {
  test('independent contract, not model-authored', () {
    final d = <int>[2, -3, 4, 0, 9];
    if (runningProducts(d).toString() != '[2, -6, -24, 0, 0]')
      throw StateError('products');
    if (runningProducts(<int>[]).isNotEmpty) throw StateError('empty');
    if (runningProducts(<int>[-2, -2]).toString() != '[-2, 4]')
      throw StateError('negatives');
    if (d.length != 5) throw StateError('mutation');
    print(
        'PASS: independent Dart consumer for original model-generated running_product');
  });
}
