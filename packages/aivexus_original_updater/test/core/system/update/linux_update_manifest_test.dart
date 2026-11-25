import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const sha =
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  test('parses, selects and serializes verified Linux Debian metadata', () {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.0.15+2201',
      'versionCode': 2201,
      'apkUrl': 'https://example.com/app-release.apk',
      'linuxUrl': 'https://example.com/AI-Orchestrator-Linux-amd64.deb',
      'linuxFileName': 'AI-Orchestrator-Linux-amd64.deb',
      'linuxSizeBytes': 25165824,
      'linuxSha256': sha,
    });

    final artifact = manifest.artifactFor(UpdateTargetPlatform.linux);
    expect(artifact, isNotNull);
    expect(artifact!.fileName, 'AI-Orchestrator-Linux-amd64.deb');
    expect(artifact.url, 'https://example.com/AI-Orchestrator-Linux-amd64.deb');
    expect(artifact.sizeBytes, 25165824);
    expect(artifact.sha256, sha);

    final encoded = manifest.toJson();
    expect(encoded['linux_url'], artifact.url);
    expect(encoded['linux_file_name'], artifact.fileName);
    expect(encoded['linux_size_bytes'], artifact.sizeBytes);
    expect(encoded['linux_sha256'], sha);
  });

  test('derives Linux file name from URL when omitted', () {
    final manifest = UpdateManifest.fromJson(const {
      'version': '1.0.15+2202',
      'apk_url': 'https://example.com/app-release.apk',
      'linux_url': 'https://example.com/AI-Orchestrator-Linux-amd64.deb',
      'linux_size_bytes': 1024,
      'linux_sha256': sha,
    });

    expect(manifest.linuxArtifact, isNotNull);
    expect(manifest.linuxArtifact!.fileName, 'AI-Orchestrator-Linux-amd64.deb');
  });

  test('rejects malformed Linux installer metadata', () {
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.15+2203',
        'apk_url': 'https://example.com/app-release.apk',
        'linux_url': 'https://example.com/update.tar.gz',
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.15+2203',
        'apk_url': 'https://example.com/app-release.apk',
        'linux_url': 'https://example.com/update.deb',
        'linux_size_bytes': 0,
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.15+2203',
        'apk_url': 'https://example.com/app-release.apk',
        'linux_url': 'https://example.com/update.deb',
        'linux_sha256': 'not-a-sha',
      }),
      throwsFormatException,
    );
  });
}
