import 'dart:convert';

import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
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
  const releaseUrl =
      'https://github.com/pilialvu75-hue/Ai-orchestrator-riserva/releases/'
      'download/v1.0.15-beta%2B103480/app-release.apk';

  Future<UpdateManager> manager({
    required String installedVersion,
    required ReleaseChannel preferredChannel,
    int? remoteBuild = 103480,
    String remoteAppVersion = '1.0.15',
    bool androidBetaComparison = true,
    int? olderOrNewerStableBuild,
  }) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final preferences = await SharedPreferences.getInstance();
    final client = MockClient((request) async {
      if (request.url.host == 'api.github.com') {
        return http.Response(
          jsonEncode(<Map<String, Object>>[
            if (olderOrNewerStableBuild != null)
              <String, Object>{
                'tag_name': 'v$remoteAppVersion+$olderOrNewerStableBuild',
                'prerelease': false,
                'draft': false,
                'body': 'Older or newer stable build',
                'assets': <Map<String, Object>>[
                  <String, Object>{
                    'name': 'app-release.apk',
                    'browser_download_url':
                        'https://github.com/pilialvu75-hue/'
                        'Ai-orchestrator-riserva/releases/download/'
                        'v$remoteAppVersion%2B$olderOrNewerStableBuild/'
                        'app-release.apk',
                    'size': 203029315,
                  },
                ],
              },
            <String, Object>{
              'tag_name': remoteBuild == null
                  ? 'v$remoteAppVersion-beta'
                  : 'v$remoteAppVersion-beta+$remoteBuild',
              'prerelease': true,
              'draft': false,
              'body': 'Image LOCAL via ML Kit',
              'assets': <Map<String, Object>>[
                <String, Object>{
                  'name': 'app-release.apk',
                  'browser_download_url': releaseUrl,
                  'size': 203029315,
                }
              ],
            },
          ]),
          200,
        );
      }
      // Deliberately stale version.json; GitHub Release must win.
      return http.Response(
        jsonEncode(<String, Object>{
          'versionName': '1.0.12+115',
          'versionCode': 12,
          'channel': 'stable',
          'apkUrl': 'https://example.org/old.apk',
        }),
        200,
      );
    });
    final checker = UpdateChecker(
      httpClient: client,
      preferences: preferences,
      comparator: comparator,
      manifestUrl: 'https://example.org/version.json',
      githubOwner: 'pilialvu75-hue',
      githubRepo: 'Ai-orchestrator-riserva',
      targetPlatform: UpdateTargetPlatform.android,
    );
    final updater = UpdateManager(
      updateChecker: checker,
      comparator: comparator,
      preferences: preferences,
      intentHandler: _FakeIntentHandler(),
      currentVersion: installedVersion,
      enableAndroidBetaBuildNumberComparison: androidBetaComparison,
    );
    updater.state.value = updater.state.value.copyWith(
      preferredChannel: preferredChannel,
    );
    return updater;
  }

  test('S24: published 103480 is detected over installed 103459', () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.beta,
    );
    // Android strips "-beta" from versionName and exposes buildNumber
    // separately: PackageInfo becomes 1.0.15+103459.
    expect(updater.currentVersion, 'v1.0.15.103459');
    expect(
      comparator.compare('v1.0.15.103480-beta', updater.currentVersion),
      lessThan(0),
      reason: 'Strict SemVer explains the original OTA regression.',
    );

    await updater.checkForUpdates(allowCachedFallback: false);

    expect(updater.state.value.status, UpdateStatus.updateAvailable);
    expect(updater.state.value.latestManifest?.version,
        'v1.0.15.103480-beta');
    expect(updater.state.value.latestManifest?.apkUrl, releaseUrl);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isTrue);
  });

  test('S24 Beta opt-in chooses 103581 over older stable 103569',
      () async {
    final updater = await manager(
      installedVersion: '1.0.15+103569',
      preferredChannel: ReleaseChannel.beta,
      remoteBuild: 103581,
      olderOrNewerStableBuild: 103569,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.updateAvailable);
    expect(updater.state.value.latestManifest?.version,
        'v1.0.15.103581-beta');
    expect(updater.hasDetectedNewerVersion(updater.state.value), isTrue);
  });

  test('S24 opted-in Beta never replaces newer stable with older beta',
      () async {
    final updater = await manager(
      installedVersion: '1.0.15+103581',
      preferredChannel: ReleaseChannel.beta,
      remoteBuild: 103575,
      olderOrNewerStableBuild: 103581,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.state.value.latestManifest?.version,
        'v1.0.15.103581');
  });

  test('S24 Stable channel ignores newer beta when a stable is present',
      () async {
    final updater = await manager(
      installedVersion: '1.0.15+103569',
      preferredChannel: ReleaseChannel.stable,
      remoteBuild: 103581,
      olderOrNewerStableBuild: 103569,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.state.value.latestManifest?.version,
        'v1.0.15.103569');
  });

  test('same beta build is never offered as an update', () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.beta,
      remoteBuild: 103459,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  test('lower beta build is not offered (Android downgrade protection)',
      () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.beta,
      remoteBuild: 103458,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  test('stable preference cannot discover or upgrade to beta', () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.stable,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  test('different app release is never overridden by beta buildCode',
      () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.beta,
      remoteAppVersion: '1.0.14',
      remoteBuild: 103999,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  test('desktop updater retains ordinary SemVer precedence', () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.beta,
      androidBetaComparison: false,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });

  test('beta target without numeric buildCode cannot override SemVer',
      () async {
    final updater = await manager(
      installedVersion: '1.0.15+103459',
      preferredChannel: ReleaseChannel.beta,
      remoteBuild: null,
    );
    await updater.checkForUpdates(allowCachedFallback: false);
    expect(updater.state.value.status, UpdateStatus.upToDate);
    expect(updater.hasDetectedNewerVersion(updater.state.value), isFalse);
  });
}
