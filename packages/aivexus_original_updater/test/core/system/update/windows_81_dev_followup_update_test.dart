import 'dart:convert';

import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/windows_update_manager.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeIntentHandler extends Mock implements AndroidIntentHandler {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const hash =
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  Future<WindowsUpdateManager> makeUpdater({
    required String currentVersion,
    required ReleaseChannel channel,
  }) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await SharedPreferences.getInstance();
    final client = MockClient((request) async {
      if (request.url.host != 'api.github.com') {
        return http.Response('not found', 404);
      }
      final versions = <String>[
        'v1.0.16-dev+100002',
        'v1.0.16-dev+100001',
        'v1.0.15-beta+104238',
        'v1.0.15+104018',
      ];
      final releases = versions.map((tag) => <String, Object>{
            'tag_name': tag,
            'draft': false,
            'prerelease': tag.contains('-'),
            'assets': <Map<String, Object>>[
              <String, Object>{
                'name': 'AI-Orchestrator-Setup-x64.exe',
                'browser_download_url':
                    'https://github.com/example/repo/releases/download/'
                        '$tag/AI-Orchestrator-Setup-x64.exe',
                'size': 42000000,
                'digest': 'sha256:$hash',
              },
            ],
          });
      return http.Response(jsonEncode(releases.toList()), 200);
    });
    final checker = UpdateChecker(
      httpClient: client,
      preferences: prefs,
      comparator: const VersionComparator(),
      manifestUrl: 'https://example.com/version.json',
      githubOwner: 'example',
      githubRepo: 'repo',
      targetPlatform: UpdateTargetPlatform.windows,
    );
    final manager = WindowsUpdateManager(
      updateChecker: checker,
      comparator: const VersionComparator(),
      preferences: prefs,
      intentHandler: _FakeIntentHandler(),
      currentVersion: currentVersion,
    );
    manager.state.value =
        manager.state.value.copyWith(preferredChannel: channel);
    return manager;
  }

  test('Win8.1 Dev installed without prerelease label can receive next Dev build',
      () async {
    final updater = await makeUpdater(
      currentVersion: '1.0.16+100001',
      channel: ReleaseChannel.dev,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.updateAvailable);
    expect(updater.state.value.latestManifest!.channel, ReleaseChannel.dev);
    expect(updater.state.value.latestManifest!.version,
        'v1.0.16.100002-dev');
    expect(updater.hasDetectedNewerVersion(updater.state.value), isTrue);
    expect(updater.state.value.latestManifest!.windowsArtifact!.sha256, hash);
  });

  test('Win8.1 Dev never reoffers the installed build', () async {
    final updater = await makeUpdater(
      currentVersion: '1.0.16+100002',
      channel: ReleaseChannel.dev,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  test('Win8.1 Dev never downgrades a newer numeric build', () async {
    final updater = await makeUpdater(
      currentVersion: '1.0.16+100003',
      channel: ReleaseChannel.dev,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  for (final channel in [ReleaseChannel.stable, ReleaseChannel.beta]) {
    test('Win8.1 Dev exception cannot affect the $channel update channel',
        () async {
      final updater = await makeUpdater(
        currentVersion: '1.0.16+100001',
        channel: channel,
      );
      await updater.checkForUpdates(allowCachedFallback: false);
      expect(updater.state.value.status, UpdateStatus.upToDate);
      expect(updater.state.value.latestManifest?.channel, channel);
    });
  }
}
