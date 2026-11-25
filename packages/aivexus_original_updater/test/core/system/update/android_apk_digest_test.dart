import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';

void main() {
  final digest = List.filled(64, 'a').join();
  Map<String, dynamic> fixture() => {
    'versionName': '1.2.3', 'apkUrl': 'https://example.test/app.apk',
    'apk_size_bytes': 100000, 'apk_sha256': digest.toUpperCase(),
  };
  test('Android digest survives parse, artifact and cache serialization', () {
    final m = UpdateManifest.fromJson(fixture());
    expect(m.apkSha256, digest);
    expect(m.androidArtifact.sha256, digest);
    expect(UpdateManifest.fromJson(m.toJson()).apkSha256, digest);
  });
  test('invalid digest rejected, legacy missing digest remains parseable', () {
    expect(() => UpdateManifest.fromJson(fixture()..['apk_sha256'] = 'bad'), throwsFormatException);
    expect(UpdateManifest.fromJson(fixture()..remove('apk_sha256')).apkSha256, isNull);
  });
}
