import 'package:aivexus_external_characters/aivexus_external.dart';
void main() {
 if (AivexusTextOps().graphemes('hello') != 5)
   throw StateError('real grapheme functionality failed');
 print('PASS: independently acquired public Dart source');
}
