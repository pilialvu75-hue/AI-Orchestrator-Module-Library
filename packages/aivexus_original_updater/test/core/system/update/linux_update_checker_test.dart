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
  const manifestUrl = 'https://example.com/version.json';
  const owner = 'pilialvu75-hue';
  const repo = 'Ai-orchestrator-riserva';
  const linuxSha =
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  Future<SharedPreferences> preferencesWith(
    Map<String, Object> initialValues,
  ) async {
    SharedPreferences.setMockInitialValues(initialValues);
    return SharedPreferences.getInstance();
  }

  test(
    'Linux ignores Android-only version.json and selects verified Debian asset from GitHub release',
    () async {
      final preferences = await preferencesWith(const {});
      final client = MockClient((request) async {
        if (request.url.toString() == manifestUrl) {
          return http.Response(
            jsonEncode(const {
              'versionName': '1.0.15+2200',
              'apkUrl': 'https://example.com/app-release.apk',
            }),
            200,
          );
        }
        if (request.url.host == 'api.github.com') {
          return http.Response(
            jsonEncode([
              {
                'tag_name': 'v1.0.15+2201',
                'draft': false,
                'prerelease': false,
                'body': 'Coordinated Linux release',
                'assets': [
                  {
                    'name': 'app-release.apk',
                    'browser_download_url':
                        'https://github.com/example/app-release.apk',
                    'size': 165000000,
                  },
                  {
                    'name': 'AI-Orchestrator-Linux-amd64.deb',
                    'browser_download_url':
                        'https://github.com/example/AI-Orchestrator-Linux-amd64.deb',
                    'size': 25165824,
                    'digest': 'sha256:$linuxSha',
                  },
                ],
              },
            ]),
            200,
          );
        }
        return http.Response('not found', 404);
      });

      final checker = UpdateChecker(
        httpClient: client,
        preferences: preferences,
        comparator: const VersionComparator(),
        manifestUrl: manifestUrl,
        githubOwner: owner,
        githubRepo: repo,
        targetPlatform: UpdateTargetPlatform.linux,
      );

      final result = await checker.checkLatestManifest(
        preferredChannel: ReleaseChannel.stable,
        allowCachedFallback: false,
      );

      expect(result.manifest, isNotNull);
      expect(result.manifest!.version, contains('2201'));
      expect(result.manifest!.linuxArtifact, isNotNull);
      expect(
        result.manifest!.linuxArtifact!.fileName,
        'AI-Orchestrator-Linux-amd64.deb',
      );
      expect(result.manifest!.linuxArtifact!.sizeBytes, 25165824);
      expect(result.manifest!.linuxArtifact!.sha256, linuxSha);
    },
  );

  test('Linux fails closed when Debian asset has no GitHub SHA-256 digest', () async {
    final preferences = await preferencesWith(const {});
    final client = MockClient((request) async {
      if (request.url.toString() == manifestUrl) {
        return http.Response('not found', 404);
      }
      if (request.url.host == 'api.github.com') {
        return http.Response(
          jsonEncode([
            {
              'tag_name': 'v1.0.15+2202',
              'draft': false,
              'prerelease': false,
              'assets': [
                {
                  'name': 'app-release.apk',
                  'browser_download_url':
                      'https://github.com/example/app-release.apk',
                  'size': 165000000,
                },
                {
                  'name': 'AI-Orchestrator-Linux-amd64.deb',
                  'browser_download_url':
                      'https://github.com/example/AI-Orchestrator-Linux-amd64.deb',
                  'size': 25165824,
                },
              ],
            },
          ]),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    final checker = UpdateChecker(
      httpClient: client,
      preferences: preferences,
      comparator: const VersionComparator(),
      manifestUrl: manifestUrl,
      githubOwner: owner,
      githubRepo: repo,
      targetPlatform: UpdateTargetPlatform.linux,
    );

    final result = await checker.checkLatestManifest(
      preferredChannel: ReleaseChannel.stable,
      allowCachedFallback: false,
    );

    expect(result.manifest, isNull);
  });

  test('Linux does not reuse an Android-only cached manifest', () async {
    final preferences = await preferencesWith({
      'system.update.cached_manifest': jsonEncode(const {
        'versionName': '1.0.15+2203',
        'apkUrl': 'https://example.com/app-release.apk',
      }),
    });
    final checker = UpdateChecker(
      httpClient: MockClient((_) async => http.Response('not found', 404)),
      preferences: preferences,
      comparator: const VersionComparator(),
      manifestUrl: manifestUrl,
      githubOwner: owner,
      githubRepo: repo,
      targetPlatform: UpdateTargetPlatform.linux,
    );

    final cached = await checker.getCachedManifest(
      preferredChannel: ReleaseChannel.stable,
    );

    expect(cached, isNull);
  });
}
