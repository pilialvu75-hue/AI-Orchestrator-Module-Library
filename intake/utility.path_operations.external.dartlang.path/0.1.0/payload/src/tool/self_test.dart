import 'package:aivexus_external_path/aivexus_external.dart';
void main() {
 final x = AivexusPathOps();
 if (x.join('a','b') != 'a/b' || x.normalize('a/../b') != 'b')
   throw StateError('real path functionality failed');
 print('PASS: independently acquired public Dart source');
}
