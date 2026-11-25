import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';

void main() {
  const sha = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  Map<String, dynamic> release(
    String tag, {
    bool windows = true,
    bool android = false,
  }) => <String, dynamic>{
    'tag_name': tag,
    'draft': false,
    'prerelease': true,
    'assets': <Map<String, dynamic>>[
      if (windows) <String, dynamic>{
        'name': 'AI-Orchestrator-Setup-x64.exe',
        'browser_download_url':
            'https://github.com/example/example/releases/download/$tag/'
            'AI-Orchestrator-Setup-x64.exe',
        'size': 42000000,
        'digest': 'sha256:$sha',
      },
      if (android) <String, dynamic>{
        'name': 'app-arm64-v8a-release.apk',
        'browser_download_url':
            'https://github.com/example/example/releases/download/$tag/'
            'app-arm64-v8a-release.apk',
        'size': 22000000,
      },
    ],
  };

  Future<UpdateManifest?> discover(
    UpdateTargetPlatform platform,
    ReleaseChannel channel,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final preferences = await SharedPreferences.getInstance();
    final client = MockClient((request) async {
      if (request.url.host == 'api.github.com') {
        return http.Response(jsonEncode(<Map<String, dynamic>>[
          release('v1.0.15-beta+104164', android: true),
          release('v1.0.15-beta+200001', android: false),
        ]), 200);
      }
      return http.Response('', 404);
    });
    try {
      final checker = UpdateChecker(
        httpClient: client,
        preferences: preferences,
        comparator: const VersionComparator(),
        manifestUrl: 'https://example.com/version.json',
        githubOwner: 'example',
        githubRepo: 'example',
        targetPlatform: platform,
      );
      final result = await checker.checkLatestManifest(
        preferredChannel: channel,
        allowCachedFallback: false,
      );
      return result.manifest;
    } finally {
      client.close();
    }
  }

  test('Windows Beta selects new Computer Use version, not prior beta', () async {
    final manifest = await discover(
      UpdateTargetPlatform.windows, ReleaseChannel.beta,
    );
    expect(manifest, isNotNull);
    expect(manifest!.version, 'v1.0.15.200001-beta');
    expect(manifest.windowsArtifact?.sha256, sha);
    expect(manifest.artifactFor(UpdateTargetPlatform.android), isNull);
  });

  test('Android Beta does not see Windows-only Computer Use update', () async {
    final manifest = await discover(
      UpdateTargetPlatform.android, ReleaseChannel.beta,
    );
    expect(manifest?.version, 'v1.0.15.104164-beta');
    expect(manifest?.artifactFor(UpdateTargetPlatform.android), isNotNull);
  });

  test('Stable channel cannot discover experimental Computer Use beta', () async {
    final manifest = await discover(
      UpdateTargetPlatform.windows, ReleaseChannel.stable,
    );
    expect(manifest, isNull);
  });
}
