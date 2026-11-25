import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';

class UpdateCheckResult {
  const UpdateCheckResult({
    required this.manifest,
    required this.usedCache,
    this.errorMessage,
  });

  final UpdateManifest? manifest;
  final bool usedCache;
  final String? errorMessage;
}

class _ReleaseAsset {
  const _ReleaseAsset({
    required this.name,
    required this.url,
    required this.sizeBytes,
    this.sha256,
  });

  final String name;
  final String url;
  final int sizeBytes;
  final String? sha256;
}

class UpdateChecker {
  UpdateChecker({
    required http.Client httpClient,
    required SharedPreferences preferences,
    required VersionComparator comparator,
    required this.manifestUrl,
    required this.githubOwner,
    required this.githubRepo,
    this.targetPlatform = UpdateTargetPlatform.android,
    this.requireApkSha256 = false,
    this.manifestOnly = false,
    this.windowsSetupAssetName = 'AI-Orchestrator-Setup-x64.exe',
    this.macosDmgAssetName = 'AI-Orchestrator-macOS.dmg',
    this.linuxDebAssetName = 'AI-Orchestrator-Linux-amd64.deb',
  })  : _httpClient = httpClient,
        _preferences = preferences,
        _comparator = comparator;

  final http.Client _httpClient;
  final SharedPreferences _preferences;
  final VersionComparator _comparator;

  final String manifestUrl;
  final String githubOwner;
  final String githubRepo;
  final UpdateTargetPlatform targetPlatform;
  final bool requireApkSha256;
  /// For manifest-last publication: GitHub releases are not an authorization source.
  final bool manifestOnly;

  static const String _cachedManifestLegacyKey = 'system.update.cached_manifest';
  static const String _cachedManifestKeyPrefix = 'system.update.cached_manifest.v2';
  final String windowsSetupAssetName;
  final String macosDmgAssetName;
  final String linuxDebAssetName;

  Future<UpdateCheckResult> checkLatestManifest({
    required ReleaseChannel preferredChannel,
    bool allowCachedFallback = true,
  }) async {
    _logUpdateCheck(
      'start preferred_channel=$preferredChannel target=${targetPlatform.name}',
    );
    _logVersion('version.json url: $manifestUrl');
    final errors = <String>[];
    try {
      final resolved = await Future.wait<UpdateManifest?>([
        _fetchRemoteManifestSafe(preferredChannel, errors),
        if (manifestOnly) Future<UpdateManifest?>.value(null)
        else _fetchFromGitHubReleasesSafe(preferredChannel, errors),
      ]);
      final fromManifest = resolved[0];
      final fromGitHub = resolved[1];
      final remoteLatest = _pickNewestManifest(
        fromManifest,
        fromGitHub,
        preferredChannel,
      );
      if (remoteLatest != null) {
        final artifact = remoteLatest.artifactFor(targetPlatform);
        _logVersion(
          'Resolved latest manifest version=${remoteLatest.version} '
          'versionCode=${remoteLatest.versionCode ?? '-'} '
          'target=${targetPlatform.name} url=${artifact?.url ?? '-'}',
        );
        await _cacheManifest(remoteLatest);
        return UpdateCheckResult(manifest: remoteLatest, usedCache: false);
      }
    } catch (e) {
      _logUpdate('Update check error: $e');
      errors.add(e.toString());
      if (!allowCachedFallback) {
        return UpdateCheckResult(
          manifest: null,
          usedCache: false,
          errorMessage: errors.join(' | '),
        );
      }
      final cached = await getCachedManifest(
        preferredChannel: preferredChannel,
      );
      if (cached != null) {
        _logUpdate('Using cached manifest version=${cached.version}');
        return UpdateCheckResult(
          manifest: cached,
          usedCache: true,
          errorMessage: errors.join(' | '),
        );
      }
      return UpdateCheckResult(
        manifest: null,
        usedCache: false,
        errorMessage: errors.join(' | '),
      );
    }

    _logUpdate('No remote update data, falling back to cache');
    if (!allowCachedFallback) {
      return UpdateCheckResult(
        manifest: null,
        usedCache: false,
        errorMessage:
            errors.isEmpty ? 'No update data available' : errors.join(' | '),
      );
    }
    final cached = await getCachedManifest(
      preferredChannel: preferredChannel,
    );
    return UpdateCheckResult(
      manifest: cached,
      usedCache: cached != null,
      errorMessage: cached == null
          ? (errors.isEmpty
              ? 'No update data available'
              : errors.join(' | '))
          : null,
    );
  }

  Future<UpdateManifest?> _fetchRemoteManifestSafe(
    ReleaseChannel preferredChannel,
    List<String> errors,
  ) async {
    try {
      final manifest = await _fetchRemoteManifest(preferredChannel);
      if (manifest != null) {
        _logVersion(
          'Latest from version.json: version=${manifest.version} '
          'versionCode=${manifest.versionCode ?? '-'}',
        );
      }
      return manifest;
    } catch (error) {
      _logUpdate('Manifest fetch failed: $error');
      errors.add('manifest: $error');
      return null;
    }
  }

  Future<UpdateManifest?> _fetchFromGitHubReleasesSafe(
    ReleaseChannel preferredChannel,
    List<String> errors,
  ) async {
    try {
      final manifest = await _fetchFromGitHubReleases(preferredChannel);
      if (manifest != null) {
        _logVersion(
          'Latest from GitHub releases: version=${manifest.version} '
          'versionCode=${manifest.versionCode ?? '-'}',
        );
      }
      return manifest;
    } catch (error) {
      _logUpdate('GitHub releases fetch failed: $error');
      errors.add('github: $error');
      return null;
    }
  }

  UpdateManifest? _pickNewestManifest(
    UpdateManifest? first,
    UpdateManifest? second,
    ReleaseChannel preferredChannel,
  ) {
    if (first == null) return second;
    if (second == null) return first;
    final comparison = _isNewerReleaseForChannel(
      second,
      first,
      preferredChannel,
    )
        ? 1
        : _isNewerReleaseForChannel(first, second, preferredChannel)
            ? -1
            : 0;
    _logVersion(
      'Comparing remote versions: first=${first.version} '
      'second=${second.version} compare=$comparison',
    );
    _logVersionCompare(
      'first=${first.version} second=${second.version} result=$comparison',
    );
    if (comparison >= 0) {
      _logVersion(
        'Selecting second manifest (GitHub tie-break or newer): ${second.version}',
      );
      return second;
    }
    _logVersion('Selecting first manifest: ${first.version}');
    return first;
  }

  Future<UpdateManifest?> _fetchRemoteManifest(
    ReleaseChannel preferredChannel,
  ) async {
    final uri = Uri.tryParse(manifestUrl);
    if (uri == null) {
      _logVersion('Invalid manifest URL: $manifestUrl');
      return null;
    }

    _logUpdate('Fetching remote version.json from: $uri');
    final response = await _httpClient
        .get(uri, headers: const {'Accept': 'application/json'})
        .timeout(const Duration(seconds: 15));

    _logUpdate(
      'Remote version.json response status=${response.statusCode} '
      'bytes=${response.bodyBytes.length}',
    );
    if (response.statusCode != 200 || response.body.isEmpty) {
      _logUpdate('Remote version.json unavailable or empty');
      return null;
    }

    final dynamic decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Manifest JSON must be an object');
    }
    _logVersion('Parsed version.json: $decoded');

    final manifest = UpdateManifest.fromJson(decoded);
    _logVersion(
      'Manifest parsed version=${manifest.version} '
      'versionCode=${manifest.versionCode ?? '-'} channel=${manifest.channel}',
    );
    if (!preferredChannel.allows(manifest.channel)) {
      _logVersion(
        'Manifest channel rejected: ${manifest.channel} '
        'not allowed for $preferredChannel',
      );
      return null;
    }
    if (!_supportsTarget(manifest)) {
      _logArtifactInvalid(
        'source=version_json target=${targetPlatform.name} '
        'version=${manifest.version} reason=target_asset_missing',
      );
      return null;
    }
    return manifest;
  }

  Future<UpdateManifest?> _fetchFromGitHubReleases(
    ReleaseChannel preferredChannel,
  ) async {
    final uri = Uri.parse(
      'https://api.github.com/repos/$githubOwner/$githubRepo/releases',
    );
    _logUpdate('Fetching GitHub releases metadata from: $uri');
    final response = await _httpClient.get(
      uri,
      headers: const {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    ).timeout(const Duration(seconds: 15));

    _logUpdate(
      'GitHub releases response status=${response.statusCode} '
      'bytes=${response.bodyBytes.length}',
    );
    if (response.statusCode != 200 || response.body.isEmpty) {
      _logUpdate('GitHub releases unavailable or empty');
      return null;
    }

    final dynamic decoded = jsonDecode(response.body);
    if (decoded is! List) {
      throw const FormatException('GitHub releases payload is not a list');
    }

    UpdateManifest? best;
    for (final item in decoded) {
      if (item is! Map) continue;
      final release = Map<String, dynamic>.from(item);
      if (release['draft'] == true) continue;

      final channel = _releaseChannelFromGitHubRelease(release);
      if (!preferredChannel.allows(channel)) continue;

      final tagName = (release['tag_name'] as String?)?.trim() ?? '';
      if (tagName.isEmpty) {
        _logArtifactInvalid('reason=missing_tag');
        continue;
      }

      final version = _normalizeVersionFromTag(tagName);
      if (version == null) {
        _logArtifactInvalid('reason=invalid_version tag=$tagName');
        continue;
      }
      _logVersionRemote('tag=$tagName normalized=$version');

      final apkAsset = _extractApkAsset(release);
      if (apkAsset == null && targetPlatform == UpdateTargetPlatform.android) continue;
      if (apkAsset != null) _logApkFound(
        'tag=$tagName file=${apkAsset.name} size_bytes=${apkAsset.sizeBytes}',
      );

      final windowsAsset = _extractWindowsAsset(release);
      if (windowsAsset != null) {
        _logWindowsFound(
          'tag=$tagName file=${windowsAsset.name} '
          'size_bytes=${windowsAsset.sizeBytes} sha256=${windowsAsset.sha256}',
        );
      }
      if (targetPlatform == UpdateTargetPlatform.windows &&
          windowsAsset == null) {
        _logArtifactInvalid(
          'tag=$tagName target=windows reason=setup_asset_not_found_or_unverified',
        );
        continue;
      }

      final macosAsset = _extractMacosAsset(release);
      if (macosAsset != null) {
        _logMacosFound(
          'tag=$tagName file=${macosAsset.name} '
          'size_bytes=${macosAsset.sizeBytes} sha256=${macosAsset.sha256}',
        );
      }
      if (targetPlatform == UpdateTargetPlatform.macos && macosAsset == null) {
        _logArtifactInvalid(
          'tag=$tagName target=macos reason=dmg_asset_not_found_or_unverified',
        );
        continue;
      }

      final linuxAsset = _extractLinuxAsset(release);
      if (linuxAsset != null) {
        _logLinuxFound(
          'tag=$tagName file=${linuxAsset.name} '
          'size_bytes=${linuxAsset.sizeBytes} sha256=${linuxAsset.sha256}',
        );
      }
      if (targetPlatform == UpdateTargetPlatform.linux && linuxAsset == null) {
        _logArtifactInvalid(
          'tag=$tagName target=linux reason=deb_asset_not_found_or_unverified',
        );
        continue;
      }

      final manifest = UpdateManifest(
        version: version,
        versionCode: null,
        channel: channel,
        minSupported: UpdateManifest.defaultMinSupportedVersion,
        apkUrl: apkAsset?.url ?? '',
        apkFileName: apkAsset?.name,
        apkSizeBytes: apkAsset?.sizeBytes,
        apkSha256: apkAsset?.sha256,
        windowsUrl: windowsAsset?.url,
        windowsFileName: windowsAsset?.name,
        windowsSizeBytes: windowsAsset?.sizeBytes,
        windowsSha256: windowsAsset?.sha256,
        macosUrl: macosAsset?.url,
        macosFileName: macosAsset?.name,
        macosSizeBytes: macosAsset?.sizeBytes,
        macosSha256: macosAsset?.sha256,
        linuxUrl: linuxAsset?.url,
        linuxFileName: linuxAsset?.name,
        linuxSizeBytes: linuxAsset?.sizeBytes,
        linuxSha256: linuxAsset?.sha256,
        changelog: (release['body'] as String?)?.trim() ?? '',
        critical: false,
      );

      if (!_supportsTarget(manifest)) continue;
      if (best == null ||
          _isNewerReleaseForChannel(manifest, best, preferredChannel)) {
        best = manifest;
      }
    }

    return best;
  }

  /// Official Android and Windows betas have monotonically increasing build
  /// codes. Desktop installers must honor a newer beta build when the owner
  /// selected Beta; strict SemVer would incorrectly prefer an older stable.
  /// but PackageInfo drops the beta suffix. With explicit Beta opt-in,
  /// 1.0.15-beta+103581 must outrank older 1.0.15+103569 even though
  /// conventional SemVer ranks every stable above every beta of that base.
  /// Limit this exception to known numeric four-segment Android/Windows releases
  /// with the same major/minor/patch. Other platforms and versions continue
  /// to follow SemVer. Never pick an older build or a malformed tag.
  bool _isNewerReleaseForChannel(
    UpdateManifest candidate,
    UpdateManifest current,
    ReleaseChannel preferredChannel,
  ) {
    if ((targetPlatform == UpdateTargetPlatform.android ||
            targetPlatform == UpdateTargetPlatform.windows) &&
        preferredChannel == ReleaseChannel.beta) {
      final a = _comparator.parse(candidate.version);
      final b = _comparator.parse(current.version);
      if (a != null &&
          b != null &&
          a.numericSegments.length == 4 &&
          b.numericSegments.length == 4 &&
          (a.channel == ReleaseChannel.beta ||
              a.channel == ReleaseChannel.stable) &&
          (b.channel == ReleaseChannel.beta ||
              b.channel == ReleaseChannel.stable) &&
          a.numericSegments[0] == b.numericSegments[0] &&
          a.numericSegments[1] == b.numericSegments[1] &&
          a.numericSegments[2] == b.numericSegments[2]) {
        return a.numericSegments[3] > b.numericSegments[3];
      }
    }
    return _comparator.compare(candidate.version, current.version) > 0;
  }

  ReleaseChannel _releaseChannelFromGitHubRelease(
    Map<String, dynamic> release,
  ) {
    final tagName = ((release['tag_name'] as String?) ?? '').toLowerCase();
    if (tagName.contains('nightly')) return ReleaseChannel.nightly;
    if (tagName.contains('dev')) return ReleaseChannel.dev;
    if (tagName.contains('beta')) return ReleaseChannel.beta;
    if (release['prerelease'] == true) return ReleaseChannel.beta;
    return ReleaseChannel.stable;
  }

  String? _normalizeVersionFromTag(String tag) {
    final normalized = tag.replaceFirst(RegExp(r'^v'), '');
    final directMatch = _comparator.normalize(normalized);
    if (directMatch != null) return directMatch;
    final match = RegExp(
      r'(\d+\.\d+\.\d+(?:\.\d+)*(?:-[0-9A-Za-z.-]+)?)',
    ).firstMatch(normalized);
    return match == null ? null : _comparator.normalize(match.group(1)!);
  }

  _ReleaseAsset? _extractApkAsset(Map<String, dynamic> release) {
    final assets = release['assets'];
    if (assets is! List) {
      _logApkInvalid('reason=assets_missing');
      return null;
    }

    _ReleaseAsset? fallbackAsset;
    for (final rawAsset in assets) {
      if (rawAsset is! Map) continue;
      final asset = Map<String, dynamic>.from(rawAsset);
      final candidate = _validatedReleaseAsset(
        asset,
        requiredExtension: '.apk',
        requireSha256: requireApkSha256 && targetPlatform == UpdateTargetPlatform.android,
      );
      if (candidate == null) continue;

      final name = candidate.name.toLowerCase();
      final looksLikePrimaryRelease = name.contains('app-release') ||
          name.contains('app-arm64-v8a-release');
      if (looksLikePrimaryRelease) {
        return candidate;
      }
      fallbackAsset ??= candidate;
    }

    if (fallbackAsset == null) {
      _logApkInvalid('reason=apk_asset_not_found');
    }
    return fallbackAsset;
  }

  _ReleaseAsset? _extractWindowsAsset(Map<String, dynamic> release) {
    final assets = release['assets'];
    if (assets is! List) return null;

    for (final rawAsset in assets) {
      if (rawAsset is! Map) continue;
      final asset = Map<String, dynamic>.from(rawAsset);
      final rawName = ((asset['name'] as String?) ?? '').trim();
      if (rawName.toLowerCase() != windowsSetupAssetName.toLowerCase()) {
        continue;
      }
      final candidate = _validatedReleaseAsset(
        asset,
        requiredExtension: '.exe',
        requireSha256: true,
      );
      if (candidate != null) return candidate;
    }
    return null;
  }

  _ReleaseAsset? _extractMacosAsset(Map<String, dynamic> release) {
    final assets = release['assets'];
    if (assets is! List) return null;

    for (final rawAsset in assets) {
      if (rawAsset is! Map) continue;
      final asset = Map<String, dynamic>.from(rawAsset);
      final rawName = ((asset['name'] as String?) ?? '').trim();
      if (rawName.toLowerCase() != macosDmgAssetName.toLowerCase()) {
        continue;
      }
      final candidate = _validatedReleaseAsset(
        asset,
        requiredExtension: '.dmg',
        requireSha256: true,
      );
      if (candidate != null) return candidate;
    }
    return null;
  }

  _ReleaseAsset? _extractLinuxAsset(Map<String, dynamic> release) {
    final assets = release['assets'];
    if (assets is! List) return null;

    for (final rawAsset in assets) {
      if (rawAsset is! Map) continue;
      final asset = Map<String, dynamic>.from(rawAsset);
      final rawName = ((asset['name'] as String?) ?? '').trim();
      if (rawName.toLowerCase() != linuxDebAssetName.toLowerCase()) {
        continue;
      }
      final candidate = _validatedReleaseAsset(
        asset,
        requiredExtension: '.deb',
        requireSha256: true,
      );
      if (candidate != null) return candidate;
    }
    return null;
  }

  _ReleaseAsset? _validatedReleaseAsset(
    Map<String, dynamic> asset, {
    required String requiredExtension,
    bool requireSha256 = false,
  }) {
    final rawName = ((asset['name'] as String?) ?? '').trim();
    final name = rawName.toLowerCase();
    final url = (asset['browser_download_url'] as String?)?.trim();
    final sizeBytes = switch (asset['size']) {
      int value => value,
      String value => int.tryParse(value.trim()) ?? 0,
      _ => 0,
    };

    if (rawName.isEmpty ||
        rawName.contains('/') ||
        !name.endsWith(requiredExtension)) {
      _logArtifactInvalid(
        'reason=invalid_asset_name name=$rawName expected=$requiredExtension',
      );
      return null;
    }
    if (url == null || url.isEmpty) {
      _logArtifactInvalid('reason=missing_asset_url name=$rawName');
      return null;
    }
    if (sizeBytes <= 0) {
      _logArtifactInvalid(
        'reason=invalid_asset_size name=$rawName size_bytes=$sizeBytes',
      );
      return null;
    }
    final uri = Uri.tryParse(url);
    if (uri == null ||
        !(uri.scheme == 'https' || uri.scheme == 'http') ||
        uri.host.isEmpty) {
      _logArtifactInvalid('reason=invalid_asset_url name=$rawName');
      return null;
    }

    final sha256 = _parseGitHubSha256(asset['digest']);
    if (requireSha256 && sha256 == null) {
      _logArtifactInvalid('reason=missing_sha256 name=$rawName');
      return null;
    }

    return _ReleaseAsset(
      name: rawName,
      url: url,
      sizeBytes: sizeBytes,
      sha256: sha256,
    );
  }

  String? _parseGitHubSha256(Object? rawDigest) {
    if (rawDigest is! String) return null;
    final digest = rawDigest.trim().toLowerCase();
    const prefix = 'sha256:';
    if (!digest.startsWith(prefix)) return null;
    final value = digest.substring(prefix.length);
    return RegExp(r'^[0-9a-f]{64}$').hasMatch(value) ? value : null;
  }

  bool _supportsTarget(UpdateManifest manifest) =>
      manifest.artifactFor(targetPlatform) != null &&
      (targetPlatform != UpdateTargetPlatform.android || !requireApkSha256 ||
          manifest.apkSha256 != null);

  String _cacheKeyForChannel(ReleaseChannel channel) =>
      '$_cachedManifestKeyPrefix.${channel.storageValue}';

  Future<UpdateManifest?> getCachedManifest({
    ReleaseChannel? preferredChannel,
  }) async {
    String? raw;
    if (preferredChannel != null) {
      raw = _preferences.getString(_cacheKeyForChannel(preferredChannel));
    } else {
      raw = _preferences.getString(_cacheKeyForChannel(ReleaseChannel.stable));
    }
    raw ??= _preferences.getString(_cachedManifestLegacyKey);
    if (raw == null || raw.isEmpty) return null;

    try {
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final manifest = UpdateManifest.fromJson(decoded);
      if (preferredChannel != null &&
          !preferredChannel.allows(manifest.channel)) {
        return null;
      }
      if (!_supportsTarget(manifest)) {
        _logArtifactInvalid(
          'source=cache target=${targetPlatform.name} '
          'version=${manifest.version} reason=target_asset_missing',
        );
        return null;
      }
      return manifest;
    } catch (error) {
      _logUpdate('Cached manifest decode failed: $error');
      return null;
    }
  }

  Future<void> _cacheManifest(UpdateManifest manifest) async {
    final key = _cacheKeyForChannel(manifest.channel);
    _logUpdate('Caching manifest version=${manifest.version} key=$key');
    await _preferences.setString(
      key,
      jsonEncode(manifest.toJson()),
    );
  }

  Future<void> clearCachedManifest({
    ReleaseChannel? preferredChannel,
    bool clearLegacy = true,
  }) async {
    if (preferredChannel != null) {
      await _preferences.remove(_cacheKeyForChannel(preferredChannel));
    } else {
      for (final channel in ReleaseChannel.values) {
        await _preferences.remove(_cacheKeyForChannel(channel));
      }
    }
    if (clearLegacy) {
      await _preferences.remove(_cachedManifestLegacyKey);
    }
  }

  void _logUpdate(String message) => debugPrint('[UPDATE] $message');
  void _logVersion(String message) => debugPrint('[VERSION] $message');
  void _logUpdateCheck(String message) =>
      debugPrint('[UPDATE_CHECK] $message');
  void _logVersionRemote(String message) =>
      debugPrint('[UPDATE_VERSION_REMOTE] $message');
  void _logVersionCompare(String message) =>
      debugPrint('[UPDATE_VERSION_COMPARE] $message');
  void _logApkFound(String message) =>
      debugPrint('[UPDATE_APK_FOUND] $message');
  void _logApkInvalid(String message) =>
      debugPrint('[UPDATE_APK_INVALID] $message');
  void _logWindowsFound(String message) =>
      debugPrint('[UPDATE_WINDOWS_FOUND] $message');
  void _logMacosFound(String message) =>
      debugPrint('[UPDATE_MACOS_FOUND] $message');
  void _logLinuxFound(String message) =>
      debugPrint('[UPDATE_LINUX_FOUND] $message');
  void _logArtifactInvalid(String message) =>
      debugPrint('[UPDATE_ARTIFACT_INVALID] $message');
}
