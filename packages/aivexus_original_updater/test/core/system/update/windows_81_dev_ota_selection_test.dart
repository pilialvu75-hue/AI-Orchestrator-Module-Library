import 'dart:convert';

import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const digest = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
  const installedVersion = '1.0.12.2';

  Map<String, dynamic> windowsRelease(String tag, {required bool prerelease}) {
    return <String, dynamic>{
      'tag_name': tag,
      'draft': false,
      'prerelease': prerelease,
      'assets': <Map<String, dynamic>>[
        <String, dynamic>{
          'name': 'AI-Orchestrator-Setup-x64.exe',
          'browser_download_url':
              'https://github.com/example/repo/releases/download/'
              '$tag/AI-Orchestrator-Setup-x64.exe',
          'size': 42000000,
          'digest': 'sha256:$digest',
        },
      ],
    };
  }

  Future<UpdateManifest?> latest(ReleaseChannel channel) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    final client = MockClient((request) async {
      if (request.url.host == 'api.github.com') {
        return http.Response(
          jsonEncode(<Map<String, dynamic>>[
            // The Windows 8.1 unsigned-with-recovery installer must be visible
            // only after explicit Dev opt-in, never on ordinary Beta/Stable.
            windowsRelease('v1.0.16-dev+105000', prerelease: true),
            windowsRelease('v1.0.15-beta+104238', prerelease: true),
            windowsRelease('v1.0.15+104018', prerelease: false),
            // A newer Dev release without Windows assets is NOT a Windows update.
            <String, dynamic>{
              'tag_name': 'v1.0.17-dev+105010',
              'draft': false,
              'prerelease': true,
              'assets': <Map<String, dynamic>>[
                <String, dynamic>{
                  'name': 'app-release.apk',
                  'browser_download_url': 'https://example.com/app-release.apk',
                  'size': 150000000,
                }
              ]
            },
          ]),
          200,
        );
      }
      return http.Response('not found', 404);
    });
    try {
      final checker = UpdateChecker(
        httpClient: client,
        preferences: preferences,
        comparator: const VersionComparator(),
        manifestUrl: 'https://example.com/version.json',
        githubOwner: 'example',
        githubRepo: 'repo',
        targetPlatform: UpdateTargetPlatform.windows,
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

  test('Windows 8.1 Dev opt-in discovers recoverable 1.0.16 installer', () async {
    const comparator = VersionComparator();
    final result = await latest(ReleaseChannel.dev);
    expect(result, isNotNull);
    expect(result!.channel, ReleaseChannel.dev);
    expect(result.version, contains('1.0.16'));
    expect(comparator.compare(result.version, installedVersion), greaterThan(0));
    expect(result.windowsArtifact!.fileName, 'AI-Orchestrator-Setup-x64.exe');
    expect(result.windowsArtifact!.sizeBytes, 42000000);
    expect(result.windowsArtifact!.sha256, digest);
  });

  test('Windows Beta does not offer Windows 8.1-only Dev installer', () async {
    final result = await latest(ReleaseChannel.beta);
    expect(result, isNotNull);
    expect(result!.channel, ReleaseChannel.beta);
    expect(result.version, contains('1.0.15'));
    expect(result.windowsArtifact!.sha256, digest);
  });

  test('Windows Stable does not offer Windows 8.1-only Dev installer', () async {
    final result = await latest(ReleaseChannel.stable);
    expect(result, isNotNull);
    expect(result!.channel, ReleaseChannel.stable);
    expect(result.version, contains('1.0.15'));
    expect(result.windowsArtifact!.sha256, digest);
  });
}
