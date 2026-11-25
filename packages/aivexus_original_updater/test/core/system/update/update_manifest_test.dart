import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';

void main() {
  test('parses valid manifest', () {
    final manifest = UpdateManifest.fromJson(const {
      'version': '1.0.8.12',
      'channel': 'stable',
      'min_supported': '1.0.5',
      'apk_url': 'https://example.com/app.apk',
      'changelog': 'Fixes and improvements',
      'critical': false,
    });

    expect(manifest.version, 'v1.0.8.12');
    expect(manifest.channel, ReleaseChannel.stable);
    expect(manifest.minSupported, 'v1.0.5');
    expect(manifest.apkUrl, 'https://example.com/app.apk');
    expect(manifest.apkFileName, 'app.apk');
    expect(manifest.critical, isFalse);
    expect(manifest.windowsArtifact, isNull);
    expect(manifest.macosArtifact, isNull);
  });

  test('parses simplified version.json format (versionName/apkUrl/forceUpdate)', () {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.0.12.105',
      'versionCode': 12,
      'apkUrl': 'https://example.com/app-release.apk',
      'changelog': 'OTA fix release',
      'forceUpdate': false,
    });

    expect(manifest.version, 'v1.0.12.105');
    expect(manifest.apkUrl, 'https://example.com/app-release.apk');
    expect(manifest.minSupported, 'v0.0.0');
    expect(manifest.apkFileName, 'app-release.apk');
    expect(manifest.critical, isFalse);
  });

  test('parses and selects Windows installer metadata without changing Android payload', () {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.0.13.200',
      'versionCode': 13,
      'apkUrl': 'https://example.com/app-release.apk',
      'windowsUrl': 'https://example.com/AI-Orchestrator-Setup-x64.exe',
      'windowsFileName': 'AI-Orchestrator-Setup-x64.exe',
      'windowsSizeBytes': 41447219,
      'windowsSha256':
          '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    });

    final android = manifest.artifactFor(UpdateTargetPlatform.android);
    final windows = manifest.artifactFor(UpdateTargetPlatform.windows);

    expect(android, isNotNull);
    expect(android!.fileName, 'app-release.apk');
    expect(android.url, 'https://example.com/app-release.apk');
    expect(windows, isNotNull);
    expect(windows!.fileName, 'AI-Orchestrator-Setup-x64.exe');
    expect(windows.url, 'https://example.com/AI-Orchestrator-Setup-x64.exe');
    expect(windows.sizeBytes, 41447219);
    expect(
      windows.sha256,
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    );
  });

  test('parses and selects macOS DMG metadata without changing other targets', () {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.0.14.300',
      'versionCode': 14,
      'apkUrl': 'https://example.com/app-release.apk',
      'windowsUrl': 'https://example.com/AI-Orchestrator-Setup-x64.exe',
      'windowsSizeBytes': 41447219,
      'windowsSha256':
          '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
      'macosUrl': 'https://example.com/AI-Orchestrator-macOS.dmg',
      'macosFileName': 'AI-Orchestrator-macOS.dmg',
      'macosSizeBytes': 73400320,
      'macosSha256':
          'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd',
    });

    final android = manifest.artifactFor(UpdateTargetPlatform.android);
    final windows = manifest.artifactFor(UpdateTargetPlatform.windows);
    final macos = manifest.artifactFor(UpdateTargetPlatform.macos);

    expect(android, isNotNull);
    expect(windows, isNotNull);
    expect(macos, isNotNull);
    expect(macos!.fileName, 'AI-Orchestrator-macOS.dmg');
    expect(macos.url, 'https://example.com/AI-Orchestrator-macOS.dmg');
    expect(macos.sizeBytes, 73400320);
    expect(
      macos.sha256,
      'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd',
    );
  });

  test('serializes Windows installer metadata for persisted/cached manifests', () {
    final manifest = UpdateManifest.fromJson(const {
      'version': '1.0.13',
      'apk_url': 'https://example.com/app.apk',
      'windows_url': 'https://example.com/AI-Orchestrator-Setup-x64.exe',
      'windows_size_bytes': 1024,
      'windows_sha256':
          'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd',
    });

    final encoded = manifest.toJson();
    expect(encoded['windows_url'],
        'https://example.com/AI-Orchestrator-Setup-x64.exe');
    expect(encoded['windows_file_name'], 'AI-Orchestrator-Setup-x64.exe');
    expect(encoded['windows_size_bytes'], 1024);
    expect(
      encoded['windows_sha256'],
      'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd',
    );
  });

  test('serializes macOS installer metadata for persisted/cached manifests', () {
    final manifest = UpdateManifest.fromJson(const {
      'version': '1.0.14',
      'apk_url': 'https://example.com/app.apk',
      'macos_url': 'https://example.com/AI-Orchestrator-macOS.dmg',
      'macos_size_bytes': 2048,
      'macos_sha256':
          '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    });

    final encoded = manifest.toJson();
    expect(encoded['macos_url'], 'https://example.com/AI-Orchestrator-macOS.dmg');
    expect(encoded['macos_file_name'], 'AI-Orchestrator-macOS.dmg');
    expect(encoded['macos_size_bytes'], 2048);
    expect(
      encoded['macos_sha256'],
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    );
  });

  test('forceUpdate:true maps to critical:true', () {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.0.13',
      'apkUrl': 'https://example.com/app.apk',
      'forceUpdate': true,
    });
    expect(manifest.critical, isTrue);
  });

  test('throws on missing required fields', () {
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.8',
      }),
      throwsFormatException,
    );
  });

  test('throws on malformed versions and invalid apk metadata', () {
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0',
        'apk_url': 'https://example.com/app.apk',
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.12',
        'apk_url': 'https://example.com/not-an-apk.zip',
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.12',
        'apk_url': 'https://example.com/app.apk',
        'apk_size_bytes': 0,
      }),
      throwsFormatException,
    );
  });

  test('rejects malformed Windows installer metadata', () {
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.13',
        'apk_url': 'https://example.com/app.apk',
        'windows_url': 'https://example.com/setup.zip',
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.13',
        'apk_url': 'https://example.com/app.apk',
        'windows_url': 'https://example.com/setup.exe',
        'windows_size_bytes': 0,
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.13',
        'apk_url': 'https://example.com/app.apk',
        'windows_url': 'https://example.com/setup.exe',
        'windows_sha256': 'not-a-sha',
      }),
      throwsFormatException,
    );
  });

  test('rejects malformed macOS installer metadata', () {
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.14',
        'apk_url': 'https://example.com/app.apk',
        'macos_url': 'https://example.com/app.zip',
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.14',
        'apk_url': 'https://example.com/app.apk',
        'macos_url': 'https://example.com/app.dmg',
        'macos_size_bytes': 0,
      }),
      throwsFormatException,
    );
    expect(
      () => UpdateManifest.fromJson(const {
        'version': '1.0.14',
        'apk_url': 'https://example.com/app.apk',
        'macos_url': 'https://example.com/app.dmg',
        'macos_sha256': 'not-a-sha',
      }),
      throwsFormatException,
    );
  });
}
