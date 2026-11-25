import 'dart:convert';
import 'dart:io';

import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('published stable manifest never points to obsolete 1.0.12 OTA', () {
    final map = jsonDecode(File('update/version.json').readAsStringSync())
        as Map<String, dynamic>;
    const comparator = VersionComparator();
    final version = map['version'] as String;
    final build = int.tryParse(version.split('+').last);

    expect(map['channel'], 'stable');
    expect(map['versionName'], version);
    expect(comparator.compare(version, '1.0.12+115'), greaterThan(0));
    expect(build, isNotNull);
    expect(map['versionCode'], build);
    expect(map['critical'], false);
    expect(map['forceUpdate'], false);

    final apkUrl = map['apk_url'] as String;
    expect(map['apkUrl'], apkUrl);
    expect(apkUrl, startsWith(
      'https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/releases/download/',
    ));
    expect(apkUrl, contains('/v$version/app-release.apk'));
  });

  test('Stable OTA remains usable if GitHub API is unreachable', () async {
    final manifest = File('update/version.json').readAsStringSync();
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await SharedPreferences.getInstance();
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/version.json')) {
        return http.Response(manifest, 200);
      }
      return http.Response('', 503);
    });
    final checker = UpdateChecker(
      httpClient: client,
      preferences: prefs,
      comparator: const VersionComparator(),
      manifestUrl: 'https://example.org/version.json',
      githubOwner: 'pilialvu75-hue',
      githubRepo: 'Ai-orchestrator-riserva',
      targetPlatform: UpdateTargetPlatform.android,
    );

    final result = await checker.checkLatestManifest(
      preferredChannel: ReleaseChannel.stable,
      allowCachedFallback: false,
    );
    expect(result.manifest, isNotNull);
    expect(result.manifest!.channel, ReleaseChannel.stable);
    expect(result.manifest!.apkUrl, contains('/app-release.apk'));
    expect(const VersionComparator().isNewer(
      latest: result.manifest!.version,
      current: '1.0.12+115',
    ), isTrue);
  });
}
