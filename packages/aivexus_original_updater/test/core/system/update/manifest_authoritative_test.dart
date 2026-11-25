import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final status in [200, 404]) {
    test('manifest-only never discovers unpublished release (HTTP $status)', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      var githubRequests = 0;
      final client = MockClient((request) async {
        if (request.url.host == 'api.github.com') {
          githubRequests++;
          return http.Response('[]', 200);
        }
        return http.Response(jsonEncode({
          'versionName': '1.2.3',
          'apkUrl': 'https://example.test/app-release.apk',
          'apk_sha256': List.filled(64, 'a').join(),
        }), status);
      });
      final checker = UpdateChecker(httpClient: client, preferences: prefs,
        comparator: const VersionComparator(), manifestUrl: 'https://example.test/version.json',
        githubOwner: 'example', githubRepo: 'demo',
        manifestOnly: true, requireApkSha256: true);
      final result = await checker.checkLatestManifest(
        preferredChannel: ReleaseChannel.stable, allowCachedFallback: false);
      expect(githubRequests, 0);
      if (status == 200) {
        expect(result.manifest?.version, 'v1.2.3');
      } else {
        expect(result.manifest, isNull);
      }
    });
  }
}
