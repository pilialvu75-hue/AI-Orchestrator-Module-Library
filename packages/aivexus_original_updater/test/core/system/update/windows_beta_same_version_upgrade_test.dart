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

  const comparator = VersionComparator();
  const digest = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  Future<WindowsUpdateManager> createUpdater({
    required String installedVersion,
    required ReleaseChannel channel,
    int stableBuild = 103691,
    int betaBuild = 103825,
    String appVersion = '1.0.15',
  }) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final preferences = await SharedPreferences.getInstance();
    Map<String, Object> release(int build, {required bool isBeta}) {
      final tag = 'v$appVersion' + (isBeta ? '-beta' : '') + '+$build';
      return <String, Object>{
        'tag_name': tag,
        'draft': false,
        'prerelease': isBeta,
        'assets': <Map<String, Object>>[
          <String, Object>{
            'name': 'AI-Orchestrator-Setup-x64.exe',
            'browser_download_url':
                'https://github.com/example/repo/releases/download/'
                '$tag/AI-Orchestrator-Setup-x64.exe',
            'size': 43273236,
            'digest': 'sha256:$digest',
          }
        ],
      };
    }

    final client = MockClient((request) async {
      if (request.url.host == 'api.github.com') {
        // The newer beta must win with explicit Beta opt-in even if
        // the older stable appears first in GitHub's response.
        return http.Response(
          jsonEncode(<Map<String, Object>>[
            release(stableBuild, isBeta: false),
            release(betaBuild, isBeta: true),
          ]),
          200,
        );
      }
      return http.Response(
        jsonEncode(<String, Object>{
          'versionName': '1.0.12+100',
          'versionCode': 100,
          'channel': 'stable',
          'apkUrl': 'https://example.com/old-only-android.apk',
        }),
        200,
      );
    });
    final checker = UpdateChecker(
      httpClient: client,
      preferences: preferences,
      comparator: comparator,
      manifestUrl: 'https://example.com/version.json',
      githubOwner: 'example',
      githubRepo: 'repo',
      targetPlatform: UpdateTargetPlatform.windows,
    );
    final updater = WindowsUpdateManager(
      updateChecker: checker,
      comparator: comparator,
      preferences: preferences,
      intentHandler: _FakeIntentHandler(),
      currentVersion: installedVersion,
    );
    updater.state.value =
        updater.state.value.copyWith(preferredChannel: channel);
    return updater;
  }

  test('Windows Beta offers newer signed installer over older stable build',
      () async {
    final updater = await createUpdater(
      installedVersion: '1.0.15+103691',
      channel: ReleaseChannel.beta,
    );
    expect(
      comparator.compare('v1.0.15.103825-beta', updater.currentVersion),
      lessThan(0),
      reason: 'Strict SemVer previously hid the signed Windows beta.',
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.updateAvailable);
    expect(
      updater.state.value.latestManifest?.version,
      'v1.0.15.103825-beta',
    );
    expect(
      updater.state.value.latestManifest?.windowsArtifact?.sha256,
      digest,
    );
    expect(updater.hasDetectedNewerVersion(updater.state.value), isTrue);
  });

  test('Windows Stable ignores beta, even with a larger build number',
      () async {
    final updater = await createUpdater(
      installedVersion: '1.0.15+103691',
      channel: ReleaseChannel.stable,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.state.value.latestManifest?.version, 'v1.0.15.103691');
  });

  test('Windows Beta never downgrades a newer installed stable build',
      () async {
    final updater = await createUpdater(
      installedVersion: '1.0.15+103900',
      channel: ReleaseChannel.beta,
      stableBuild: 103900,
      betaBuild: 103825,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.state.value.latestManifest?.version, 'v1.0.15.103900');
  });

  test('Windows Beta does not reoffer the already installed beta build',
      () async {
    final updater = await createUpdater(
      installedVersion: '1.0.15+103825',
      channel: ReleaseChannel.beta,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });
}
