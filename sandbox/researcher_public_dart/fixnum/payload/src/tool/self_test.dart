import 'package:aivexus_external_fixnum/aivexus_external.dart';
void main() {
 if (AivexusIntOps().sum(3, 8) != 11)
   throw StateError('real fixed integer functionality failed');
 print('PASS: independently acquired public Dart source');
}
