import 'package:path/path.dart' as p;
class AivexusPathOps {
 String join(String a, String b) => p.posix.join(a, b);
 String normalize(String s) => p.posix.normalize(s);
}
