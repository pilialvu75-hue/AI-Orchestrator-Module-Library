import 'dart:convert';

import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/version_parser.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const comparator = VersionComparator();
  const parser = VersionParser();

  test('official beta tag is valid and newer than previous stable', () {
    final parsed = parser.parse('v1.0.15-beta+103466');
    expect(parsed, isNotNull);
    expect(parsed!.channel, ReleaseChannel.beta);
    expect(parsed.numericSegments, <int>[1, 0, 15, 103466]);
    expect(comparator.compare(parsed.displayValue, 'v1.0.14+103442'),
        greaterThan(0));
    expect(comparator.compare('v1.0.14+103456-beta', 'v1.0.14+103442'),
        lessThan(0)); // Older, non-SemVer tag cannot provide the upgrade.
  });

  Future<UpdateChecker> checker() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final preferences = await SharedPreferences.getInstance();
    final client = MockClient((request) async {
      if (request.url.host == 'api.github.com') {
        Map<String, Object> release(String tag, bool prerelease, int size) =>
            <String, Object>{
              'tag_name': tag,
              'draft': false,
              'prerelease': prerelease,
              'body': 'Test release',
              'assets': <Map<String, Object>>[
                <String, Object>{
                  'name': 'app-arm64-v8a-release.apk',
                  'size': size,
                  'browser_download_url':
                      'https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/releases/download/$tag/app-arm64-v8a-release.apk',
                }
              ]
            };
        return http.Response(
          jsonEncode(<Map<String, Object>>[
            release('v1.0.14+103442', false, 160000000),
            release('v1.0.14+103456-beta', true, 160000001),
            release('v1.0.15-beta+103466', true, 160000002),
          ]),
          200,
        );
      }
      return http.Response('Not found', 404);
    });
    return UpdateChecker(
      httpClient: client,
      preferences: preferences,
      comparator: comparator,
      manifestUrl: 'https://example.org/version.json',
      githubOwner: 'pilialvu75-hue',
      githubRepo: 'Ai-orchestrator-riserva',
      targetPlatform: UpdateTargetPlatform.android,
    );
  }

  test('Beta channel discovers official 1.0.15 asset through Aggiorna',
      () async {
    final result = await (await checker()).checkLatestManifest(
      preferredChannel: ReleaseChannel.beta,
      allowCachedFallback: false,
    );
    expect(result.manifest, isNotNull);
    expect(result.manifest!.channel, ReleaseChannel.beta);
    expect(result.manifest!.version, 'v1.0.15.103466-beta');
    expect(result.manifest!.apkUrl,
        contains('/v1.0.15-beta+103466/app-arm64-v8a-release.apk'));
    expect(comparator.compare(result.manifest!.version, 'v1.0.14+103442'),
        greaterThan(0));
    expect(result.usedCache, isFalse);
  });

  test('Stable channel never receives a beta, even when newer',
      () async {
    final result = await (await checker()).checkLatestManifest(
      preferredChannel: ReleaseChannel.stable,
      allowCachedFallback: false,
    );
    expect(result.manifest!.version, 'v1.0.14.103442');
    expect(result.manifest!.channel, ReleaseChannel.stable);
  });
}
