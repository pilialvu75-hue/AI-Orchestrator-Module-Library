import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/version_parser.dart';

enum UpdateTargetPlatform {
  android,
  windows,
  macos,
  linux,
}

class UpdateArtifact {
  const UpdateArtifact({
    required this.url,
    required this.fileName,
    this.sizeBytes,
    this.sha256,
  });

  final String url;
  final String fileName;
  final int? sizeBytes;
  final String? sha256;
}

class UpdateManifest {
  static const String defaultMinSupportedVersion = '0.0.0';

  const UpdateManifest({
    required this.version,
    this.versionCode,
    required this.channel,
    required this.minSupported,
    required this.apkUrl,
    this.apkFileName,
    this.apkSizeBytes,
    this.windowsUrl,
    this.windowsFileName,
    this.windowsSizeBytes,
    this.windowsSha256,
    this.macosUrl,
    this.macosFileName,
    this.macosSizeBytes,
    this.macosSha256,
    this.linuxUrl,
    this.linuxFileName,
    this.linuxSizeBytes,
    this.linuxSha256,
    required this.changelog,
    required this.critical,
  });

  final String version;
  final int? versionCode;
  final ReleaseChannel channel;
  final String minSupported;
  final String apkUrl;
  final String? apkFileName;
  final int? apkSizeBytes;
  final String? windowsUrl;
  final String? windowsFileName;
  final int? windowsSizeBytes;
  final String? windowsSha256;
  final String? macosUrl;
  final String? macosFileName;
  final int? macosSizeBytes;
  final String? macosSha256;
  final String? linuxUrl;
  final String? linuxFileName;
  final int? linuxSizeBytes;
  final String? linuxSha256;
  final String changelog;
  final bool critical;

  UpdateArtifact get androidArtifact => UpdateArtifact(
        url: apkUrl,
        fileName: apkFileName ?? Uri.parse(apkUrl).pathSegments.last,
        sizeBytes: apkSizeBytes,
      );

  UpdateArtifact? get windowsArtifact {
    final url = windowsUrl;
    final fileName = windowsFileName;
    if (url == null || fileName == null) return null;
    return UpdateArtifact(
      url: url,
      fileName: fileName,
      sizeBytes: windowsSizeBytes,
      sha256: windowsSha256,
    );
  }

  UpdateArtifact? get macosArtifact {
    final url = macosUrl;
    final fileName = macosFileName;
    if (url == null || fileName == null) return null;
    return UpdateArtifact(
      url: url,
      fileName: fileName,
      sizeBytes: macosSizeBytes,
      sha256: macosSha256,
    );
  }

  UpdateArtifact? get linuxArtifact {
    final url = linuxUrl;
    final fileName = linuxFileName;
    if (url == null || fileName == null) return null;
    return UpdateArtifact(
      url: url,
      fileName: fileName,
      sizeBytes: linuxSizeBytes,
      sha256: linuxSha256,
    );
  }

  UpdateArtifact? artifactFor(UpdateTargetPlatform target) => switch (target) {
        UpdateTargetPlatform.android => apkUrl.isEmpty ? null : androidArtifact,
        UpdateTargetPlatform.windows => windowsArtifact,
        UpdateTargetPlatform.macos => macosArtifact,
        UpdateTargetPlatform.linux => linuxArtifact,
      };

  bool isCompatibleWith({
    required String currentVersion,
    required VersionComparator comparator,
  }) {
    return comparator.isCompatible(
      currentVersion: currentVersion,
      minSupported: minSupported,
    );
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        if (versionCode != null) 'versionCode': versionCode,
        'channel': channel.storageValue,
        'min_supported': minSupported,
        'apk_url': apkUrl,
        if (apkFileName != null) 'apk_file_name': apkFileName,
        if (apkSizeBytes != null) 'apk_size_bytes': apkSizeBytes,
        if (windowsUrl != null) 'windows_url': windowsUrl,
        if (windowsFileName != null) 'windows_file_name': windowsFileName,
        if (windowsSizeBytes != null) 'windows_size_bytes': windowsSizeBytes,
        if (windowsSha256 != null) 'windows_sha256': windowsSha256,
        if (macosUrl != null) 'macos_url': macosUrl,
        if (macosFileName != null) 'macos_file_name': macosFileName,
        if (macosSizeBytes != null) 'macos_size_bytes': macosSizeBytes,
        if (macosSha256 != null) 'macos_sha256': macosSha256,
        if (linuxUrl != null) 'linux_url': linuxUrl,
        if (linuxFileName != null) 'linux_file_name': linuxFileName,
        if (linuxSizeBytes != null) 'linux_size_bytes': linuxSizeBytes,
        if (linuxSha256 != null) 'linux_sha256': linuxSha256,
        'changelog': changelog,
        'critical': critical,
      };

  static UpdateManifest fromJson(Map<String, dynamic> json) {
    const parser = VersionParser();
    // Support both the internal manifest format (version/apk_url/min_supported)
    // and the simplified version.json format (versionName/apkUrl/versionCode).
    final rawVersion = ((json['version'] ?? json['versionName']) as String?)?.trim();
    final rawApkUrl = ((json['apk_url'] ?? json['apkUrl']) as String?)?.trim() ?? '';
    final rawMinSupported = (json['min_supported'] as String?)?.trim();
    final rawVersionCode = json['versionCode'];
    final rawApkFileName =
        ((json['apk_file_name'] ?? json['apkFileName']) as String?)?.trim();
    final rawApkSizeBytes = json['apk_size_bytes'] ?? json['apkSizeBytes'];
    final rawWindowsUrl =
        ((json['windows_url'] ?? json['windowsUrl']) as String?)?.trim();
    final rawWindowsFileName =
        ((json['windows_file_name'] ?? json['windowsFileName']) as String?)?.trim();
    final rawWindowsSizeBytes =
        json['windows_size_bytes'] ?? json['windowsSizeBytes'];
    final rawWindowsSha256 =
        ((json['windows_sha256'] ?? json['windowsSha256']) as String?)?.trim();
    final rawMacosUrl =
        ((json['macos_url'] ?? json['macosUrl']) as String?)?.trim();
    final rawMacosFileName =
        ((json['macos_file_name'] ?? json['macosFileName']) as String?)?.trim();
    final rawMacosSizeBytes =
        json['macos_size_bytes'] ?? json['macosSizeBytes'];
    final rawMacosSha256 =
        ((json['macos_sha256'] ?? json['macosSha256']) as String?)?.trim();
    final rawLinuxUrl =
        ((json['linux_url'] ?? json['linuxUrl']) as String?)?.trim();
    final rawLinuxFileName =
        ((json['linux_file_name'] ?? json['linuxFileName']) as String?)?.trim();
    final rawLinuxSizeBytes =
        json['linux_size_bytes'] ?? json['linuxSizeBytes'];
    final rawLinuxSha256 =
        ((json['linux_sha256'] ?? json['linuxSha256']) as String?)?.trim();

    if (rawVersion == null || rawVersion.isEmpty) {
      throw const FormatException('Invalid manifest: missing version');
    }
    if (rawApkUrl.isEmpty && rawWindowsUrl == null && rawMacosUrl == null && rawLinuxUrl == null) {
      throw const FormatException('Invalid manifest: missing apk_url');
    }

    final parsedVersion = parser.parse(rawVersion);
    if (parsedVersion == null) {
      throw FormatException('Invalid manifest: malformed version "$rawVersion"');
    }

    final apkUri = rawApkUrl.isEmpty ? null : _validateHttpUrl(rawApkUrl, fieldName: 'apk_url');

    final derivedApkFileName =
        rawApkFileName ??
        (apkUri != null && apkUri.pathSegments.isNotEmpty ? apkUri.pathSegments.last.trim() : '');
    if (rawApkUrl.isNotEmpty && (derivedApkFileName.isEmpty ||
        derivedApkFileName.contains('/') ||
        !derivedApkFileName.toLowerCase().endsWith('.apk'))) {
      throw FormatException(
        'Invalid manifest: apk filename must be a non-empty .apk name, got: $derivedApkFileName',
      );
    }

    String? windowsUrl;
    String? windowsFileName;
    int? windowsSizeBytes;
    String? windowsSha256;
    final hasWindowsMetadata =
        rawWindowsUrl != null ||
        rawWindowsFileName != null ||
        rawWindowsSizeBytes != null ||
        rawWindowsSha256 != null;
    if (hasWindowsMetadata) {
      if (rawWindowsUrl == null || rawWindowsUrl.isEmpty) {
        throw const FormatException(
          'Invalid manifest: windows_url is required when Windows metadata is present',
        );
      }
      final windowsUri =
          _validateHttpUrl(rawWindowsUrl, fieldName: 'windows_url');
      final derivedWindowsFileName =
          rawWindowsFileName ??
          (windowsUri.pathSegments.isNotEmpty
              ? windowsUri.pathSegments.last.trim()
              : '');
      if (derivedWindowsFileName.isEmpty ||
          derivedWindowsFileName.contains('/') ||
          !derivedWindowsFileName.toLowerCase().endsWith('.exe')) {
        throw FormatException(
          'Invalid manifest: Windows filename must be a non-empty .exe name, got: $derivedWindowsFileName',
        );
      }
      windowsUrl = rawWindowsUrl;
      windowsFileName = derivedWindowsFileName;
      windowsSizeBytes = switch (rawWindowsSizeBytes) {
        int value => value,
        String value => int.tryParse(value.trim()),
        _ => null,
      };
      if (windowsSizeBytes != null && windowsSizeBytes <= 0) {
        throw FormatException(
          'Invalid manifest: Windows installer size must be > 0, got: $windowsSizeBytes',
        );
      }
      if (rawWindowsSha256 != null && rawWindowsSha256.isNotEmpty) {
        final normalizedSha = rawWindowsSha256.toLowerCase();
        if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(normalizedSha)) {
          throw const FormatException(
            'Invalid manifest: windows_sha256 must be a 64-character hexadecimal SHA-256',
          );
        }
        windowsSha256 = normalizedSha;
      }
    }

    String? macosUrl;
    String? macosFileName;
    int? macosSizeBytes;
    String? macosSha256;
    final hasMacosMetadata =
        rawMacosUrl != null ||
        rawMacosFileName != null ||
        rawMacosSizeBytes != null ||
        rawMacosSha256 != null;
    if (hasMacosMetadata) {
      if (rawMacosUrl == null || rawMacosUrl.isEmpty) {
        throw const FormatException(
          'Invalid manifest: macos_url is required when macOS metadata is present',
        );
      }
      final macosUri = _validateHttpUrl(rawMacosUrl, fieldName: 'macos_url');
      final derivedMacosFileName =
          rawMacosFileName ??
          (macosUri.pathSegments.isNotEmpty
              ? macosUri.pathSegments.last.trim()
              : '');
      if (derivedMacosFileName.isEmpty ||
          derivedMacosFileName.contains('/') ||
          !derivedMacosFileName.toLowerCase().endsWith('.dmg')) {
        throw FormatException(
          'Invalid manifest: macOS filename must be a non-empty .dmg name, got: $derivedMacosFileName',
        );
      }
      macosUrl = rawMacosUrl;
      macosFileName = derivedMacosFileName;
      macosSizeBytes = switch (rawMacosSizeBytes) {
        int value => value,
        String value => int.tryParse(value.trim()),
        _ => null,
      };
      if (macosSizeBytes != null && macosSizeBytes <= 0) {
        throw FormatException(
          'Invalid manifest: macOS installer size must be > 0, got: $macosSizeBytes',
        );
      }
      if (rawMacosSha256 != null && rawMacosSha256.isNotEmpty) {
        final normalizedSha = rawMacosSha256.toLowerCase();
        if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(normalizedSha)) {
          throw const FormatException(
            'Invalid manifest: macos_sha256 must be a 64-character hexadecimal SHA-256',
          );
        }
        macosSha256 = normalizedSha;
      }
    }

    String? linuxUrl;
    String? linuxFileName;
    int? linuxSizeBytes;
    String? linuxSha256;
    final hasLinuxMetadata =
        rawLinuxUrl != null ||
        rawLinuxFileName != null ||
        rawLinuxSizeBytes != null ||
        rawLinuxSha256 != null;
    if (hasLinuxMetadata) {
      if (rawLinuxUrl == null || rawLinuxUrl.isEmpty) {
        throw const FormatException(
          'Invalid manifest: linux_url is required when Linux metadata is present',
        );
      }
      final linuxUri = _validateHttpUrl(rawLinuxUrl, fieldName: 'linux_url');
      final derivedLinuxFileName =
          rawLinuxFileName ??
          (linuxUri.pathSegments.isNotEmpty
              ? linuxUri.pathSegments.last.trim()
              : '');
      if (derivedLinuxFileName.isEmpty ||
          derivedLinuxFileName.contains('/') ||
          !derivedLinuxFileName.toLowerCase().endsWith('.deb')) {
        throw FormatException(
          'Invalid manifest: Linux filename must be a non-empty .deb name, got: $derivedLinuxFileName',
        );
      }
      linuxUrl = rawLinuxUrl;
      linuxFileName = derivedLinuxFileName;
      linuxSizeBytes = switch (rawLinuxSizeBytes) {
        int value => value,
        String value => int.tryParse(value.trim()),
        _ => null,
      };
      if (linuxSizeBytes != null && linuxSizeBytes <= 0) {
        throw FormatException(
          'Invalid manifest: Linux installer size must be > 0, got: $linuxSizeBytes',
        );
      }
      if (rawLinuxSha256 != null && rawLinuxSha256.isNotEmpty) {
        final normalizedSha = rawLinuxSha256.toLowerCase();
        if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(normalizedSha)) {
          throw const FormatException(
            'Invalid manifest: linux_sha256 must be a 64-character hexadecimal SHA-256',
          );
        }
        linuxSha256 = normalizedSha;
      }
    }

    // Missing min_supported must never block updates by default.
    final rawResolvedMinSupported =
        (rawMinSupported != null && rawMinSupported.isNotEmpty)
            ? rawMinSupported
            : defaultMinSupportedVersion;
    final parsedMinSupported = parser.parse(rawResolvedMinSupported);
    if (parsedMinSupported == null) {
      throw FormatException(
        'Invalid manifest: malformed min_supported "$rawResolvedMinSupported"',
      );
    }
    final versionCode = switch (rawVersionCode) {
      int value => value,
      String value => int.tryParse(value.trim()),
      _ => null,
    };
    final apkSizeBytes = switch (rawApkSizeBytes) {
      int value => value,
      String value => int.tryParse(value.trim()),
      _ => null,
    };
    if (apkSizeBytes != null && apkSizeBytes <= 0) {
      throw FormatException(
        'Invalid manifest: apk size must be > 0, got: $apkSizeBytes',
      );
    }

    return UpdateManifest(
      version: parsedVersion.displayValue,
      versionCode: versionCode,
      channel: json['channel'] is String
          ? ReleaseChannel.fromString(json['channel'] as String?)
          : parsedVersion.channel,
      minSupported: parsedMinSupported.displayValue,
      apkUrl: rawApkUrl,
      apkFileName: derivedApkFileName,
      apkSizeBytes: apkSizeBytes,
      windowsUrl: windowsUrl,
      windowsFileName: windowsFileName,
      windowsSizeBytes: windowsSizeBytes,
      windowsSha256: windowsSha256,
      macosUrl: macosUrl,
      macosFileName: macosFileName,
      macosSizeBytes: macosSizeBytes,
      macosSha256: macosSha256,
      linuxUrl: linuxUrl,
      linuxFileName: linuxFileName,
      linuxSizeBytes: linuxSizeBytes,
      linuxSha256: linuxSha256,
      changelog: (json['changelog'] as String?)?.trim() ?? '',
      critical: json['critical'] == true || json['forceUpdate'] == true,
    );
  }

  static Uri _validateHttpUrl(
    String rawUrl, {
    required String fieldName,
  }) {
    final uri = Uri.tryParse(rawUrl);
    if (uri == null ||
        !(uri.scheme == 'https' || uri.scheme == 'http') ||
        uri.host.isEmpty) {
      throw FormatException(
        'Invalid manifest: $fieldName must be http/https, got: $rawUrl',
      );
    }
    return uri;
  }
}
