import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';

void main() {
  const hash = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
  for (final target in UpdateTargetPlatform.values) {
    for (final channel in [ReleaseChannel.stable, ReleaseChannel.beta]) {
      test('Windows-only beta: target=$target channel=$channel', () async {
        SharedPreferences.setMockInitialValues({});
        final preferences = await SharedPreferences.getInstance();
        final client = MockClient((request) async => request.url.host == 'api.github.com'
          ? http.Response(jsonEncode([{
              'tag_name': 'v1.0.13-beta.1', 'draft': false, 'prerelease': true,
              'assets': [{ 'name': 'AI-Orchestrator-Setup-x64.exe',
                'browser_download_url': 'https://example.com/AI-Orchestrator-Setup-x64.exe',
                'size': 43273236, 'digest': 'sha256:$hash' }],
            }]), 200)
          : http.Response('', 404));
        final checker = UpdateChecker(httpClient: client, preferences: preferences,
          comparator: const VersionComparator(), manifestUrl: 'https://example.com/version.json',
          githubOwner: 'owner', githubRepo: 'repo', targetPlatform: target);
        final result = await checker.checkLatestManifest(preferredChannel: channel, allowCachedFallback: false);
        if (target == UpdateTargetPlatform.windows && channel == ReleaseChannel.beta) {
          expect(result.manifest?.windowsArtifact?.sha256, hash);
          expect(result.manifest?.artifactFor(UpdateTargetPlatform.android), isNull);
          final cached = await checker.getCachedManifest(preferredChannel: channel);
          expect(cached?.windowsArtifact?.sha256, hash);
        } else {
          expect(result.manifest, isNull);
        }
        client.close();
      });
    }
  }
}
