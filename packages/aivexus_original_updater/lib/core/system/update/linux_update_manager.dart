import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aivexus_original_updater/core/system/update/linux_update_installer.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

/// Linux-specific facade for the shared update UI/state contract.
///
/// Discovery remains coordinated with the Android/Windows/macOS release line.
/// Linux downloads only a verified `.deb` release asset, persists it across
/// restarts, and hands installation to the desktop package handler so privilege
/// escalation stays visible and user-controlled.
class LinuxUpdateManager extends UpdateManager {
  LinuxUpdateManager({
    required UpdateChecker updateChecker,
    required VersionComparator comparator,
    required SharedPreferences preferences,
    required AndroidIntentHandler intentHandler,
    required String currentVersion,
    LinuxUpdateInstallerPort? linuxInstaller,
    Dio? dio,
  })  : _linuxComparator = comparator,
        _linuxPreferences = preferences,
        _linuxCurrentVersion = comparator.normalize(currentVersion) ?? currentVersion,
        _linuxInstaller = linuxInstaller ?? LinuxUpdateInstaller(dio: dio),
        super(
          updateChecker: updateChecker,
          comparator: comparator,
          preferences: preferences,
          intentHandler: intentHandler,
          currentVersion: currentVersion,
          dio: dio,
        );

  static const String _prefPendingPath = 'update_linux_pending_path';
  static const String _prefPendingVersion = 'update_linux_pending_version';
  static const String _prefPendingSize = 'update_linux_pending_size';
  static const String _prefPendingSha256 = 'update_linux_pending_sha256';
  static const String _prefPendingManifest = 'update_linux_pending_manifest';
  static const String _updatesDirectoryName = 'app_updates';
  static const String _linuxDirectoryName = 'linux';

  final VersionComparator _linuxComparator;
  final SharedPreferences _linuxPreferences;
  final LinuxUpdateInstallerPort _linuxInstaller;
  final String _linuxCurrentVersion;

  Timer? _linuxPeriodicTimer;
  bool _linuxDownloadInProgress = false;
  bool _linuxInstallInProgress = false;

  @override
  Future<void> startBackgroundChecks({
    bool checkOnStartup = true,
    Duration interval = const Duration(hours: 12),
  }) async {
    if (checkOnStartup) {
      await checkForUpdates();
    } else {
      await _restorePendingInstaller();
    }
    _linuxPeriodicTimer?.cancel();
    _linuxPeriodicTimer = Timer.periodic(interval, (_) {
      unawaited(checkForUpdates());
    });
  }

  @override
  void stopBackgroundChecks() {
    _linuxPeriodicTimer?.cancel();
    _linuxPeriodicTimer = null;
  }

  @override
  Future<void> checkForUpdates({
    bool allowCachedFallback = true,
  }) async {
    await super.checkForUpdates(allowCachedFallback: allowCachedFallback);
    await _restorePendingInstaller();
  }

  /// Keeps the shared/legacy method name used by existing update UI.
  @override
  Future<bool> downloadLatestApk() => _downloadLatestLinuxInstaller();

  /// Keeps the shared/legacy method name used by existing update UI.
  @override
  Future<bool> prepareInstallIntent() => _prepareLinuxInstall();

  @override
  Future<bool> forceUpdate() async {
    if (_linuxDownloadInProgress || _linuxInstallInProgress) {
      return false;
    }
    await checkForUpdates(allowCachedFallback: false);
    if (!hasDetectedNewerVersion(state.value)) {
      return false;
    }
    final downloaded = await _downloadLatestLinuxInstaller();
    if (!downloaded) return false;
    return _prepareLinuxInstall();
  }

  @override
  Future<bool> openUnknownAppsSettings() async => false;

  @override
  Future<void> refreshDiagnostics() async {
    final path = _linuxPreferences.getString(_prefPendingPath);
    if (path == null || path.isEmpty) return;
    await _restorePendingInstaller();
  }

  Future<bool> _downloadLatestLinuxInstaller() async {
    if (_linuxDownloadInProgress || _linuxInstallInProgress) {
      return false;
    }
    final manifest = state.value.latestManifest;
    final artifact = manifest?.linuxArtifact;
    if (manifest == null || artifact == null) {
      _setError('No verified Linux installer is available for this release.');
      return false;
    }
    final expectedSize = artifact.sizeBytes;
    final expectedSha256 = artifact.sha256;
    if (expectedSize == null || expectedSize <= 0 || expectedSha256 == null) {
      _setError(
        'Linux installer metadata is incomplete: size and SHA-256 are required.',
      );
      return false;
    }

    _linuxDownloadInProgress = true;
    state.value = state.value.copyWith(
      status: UpdateStatus.downloading,
      downloadProgress: 0,
      clearErrorMessage: true,
      clearTempApkPath: true,
      diagnostics: state.value.diagnostics.copyWith(
        updateUrl: artifact.url,
        apkDownloaded: false,
        clearApkPath: true,
        apkFileExists: false,
        clearInstallerLaunchSuccess: true,
        clearLastException: true,
      ),
    );

    try {
      final root = await getTemporaryDirectory();
      final versionKey = _sanitizeVersionForPath(manifest.version);
      final directory = Directory(
        p.join(
          root.path,
          _updatesDirectoryName,
          _linuxDirectoryName,
          versionKey,
        ),
      );
      await directory.create(recursive: true);
      await _cleanupObsoleteLinuxDownloads(
        root: root,
        activeVersionKey: versionKey,
      );

      final finalPath = p.join(directory.path, artifact.fileName);
      final partialPath = '$finalPath.part';
      final downloadedPath = await _linuxInstaller.download(
        url: artifact.url,
        fileName: artifact.fileName,
        finalPath: finalPath,
        partialPath: partialPath,
        expectedSizeBytes: expectedSize,
        expectedSha256: expectedSha256,
        onProgress: (received, total) {
          final progress = total > 0
              ? (received / total).clamp(0.0, 1.0).toDouble()
              : 0.0;
          state.value = state.value.copyWith(
            status: UpdateStatus.downloading,
            downloadProgress: progress,
          );
        },
      );

      await _persistPendingInstaller(
        path: downloadedPath,
        manifest: manifest,
        sizeBytes: expectedSize,
        sha256: expectedSha256,
      );
      state.value = state.value.copyWith(
        status: UpdateStatus.readyToInstall,
        tempApkPath: downloadedPath,
        downloadProgress: 1,
        clearErrorMessage: true,
        diagnostics: state.value.diagnostics.copyWith(
          updateUrl: artifact.url,
          apkDownloaded: true,
          apkPath: downloadedPath,
          apkFileExists: true,
          clearInstallerLaunchSuccess: true,
          clearLastException: true,
        ),
      );
      return true;
    } catch (error) {
      _setError('Linux installer download failed: $error');
      return false;
    } finally {
      _linuxDownloadInProgress = false;
    }
  }

  Future<bool> _prepareLinuxInstall() async {
    if (_linuxInstallInProgress || _linuxDownloadInProgress) {
      return false;
    }
    _linuxInstallInProgress = true;
    try {
      final pending = await _readPendingInstaller();
      if (pending == null) {
        _setError('No verified Linux installer is ready to install.');
        return false;
      }

      final verification = await _linuxInstaller.verify(
        filePath: pending.path,
        expectedSizeBytes: pending.sizeBytes,
        expectedSha256: pending.sha256,
      );
      if (!verification.valid) {
        await _clearPendingInstaller(deleteFile: true);
        _setError(
          'Linux installer failed verification before launch: '
          '${verification.reason}',
        );
        return false;
      }

      final launched = await _linuxInstaller.launch(pending.path);
      if (!launched) {
        _setError('Linux package installer could not be opened.');
        return false;
      }

      state.value = state.value.copyWith(
        status: UpdateStatus.readyToInstall,
        tempApkPath: pending.path,
        downloadProgress: 1,
        clearErrorMessage: true,
        diagnostics: state.value.diagnostics.copyWith(
          apkDownloaded: true,
          apkPath: pending.path,
          apkFileExists: true,
          installerLaunchSuccess: true,
          clearLastException: true,
        ),
      );
      return true;
    } catch (error) {
      _setError('Linux installer launch failed: $error');
      return false;
    } finally {
      _linuxInstallInProgress = false;
    }
  }

  Future<void> _restorePendingInstaller() async {
    final pending = await _readPendingInstaller();
    if (pending == null) return;

    if (_linuxComparator.compare(_linuxCurrentVersion, pending.version) >= 0) {
      await _clearPendingInstaller(deleteFile: true);
      if (state.value.status == UpdateStatus.readyToInstall) {
        state.value = state.value.copyWith(
          status: UpdateStatus.upToDate,
          clearTempApkPath: true,
          downloadProgress: 0,
        );
      }
      return;
    }

    final verification = await _linuxInstaller.verify(
      filePath: pending.path,
      expectedSizeBytes: pending.sizeBytes,
      expectedSha256: pending.sha256,
    );
    if (!verification.valid) {
      await _clearPendingInstaller(deleteFile: true);
      return;
    }

    final manifest = pending.manifest ?? state.value.latestManifest;
    if (manifest == null || manifest.linuxArtifact == null) {
      return;
    }
    if (_linuxComparator.compare(pending.version, manifest.version) < 0) {
      await _clearPendingInstaller(deleteFile: true);
      return;
    }

    state.value = state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      latestManifest: manifest,
      tempApkPath: pending.path,
      downloadProgress: 1,
      clearErrorMessage: true,
      diagnostics: state.value.diagnostics.copyWith(
        remoteVersion: manifest.version,
        remoteVersionCode: manifest.versionCode,
        updateUrl: manifest.linuxArtifact!.url,
        apkDownloaded: true,
        apkPath: pending.path,
        apkFileExists: true,
        clearInstallerLaunchSuccess: true,
        clearLastException: true,
      ),
    );
  }

  Future<void> _persistPendingInstaller({
    required String path,
    required UpdateManifest manifest,
    required int sizeBytes,
    required String sha256,
  }) async {
    await _linuxPreferences.setString(_prefPendingPath, path);
    await _linuxPreferences.setString(_prefPendingVersion, manifest.version);
    await _linuxPreferences.setInt(_prefPendingSize, sizeBytes);
    await _linuxPreferences.setString(_prefPendingSha256, sha256.toLowerCase());
    await _linuxPreferences.setString(
      _prefPendingManifest,
      jsonEncode(manifest.toJson()),
    );
  }

  Future<_PendingLinuxInstaller?> _readPendingInstaller() async {
    final path = _linuxPreferences.getString(_prefPendingPath);
    final version = _linuxPreferences.getString(_prefPendingVersion);
    final size = _linuxPreferences.getInt(_prefPendingSize);
    final sha = _linuxPreferences.getString(_prefPendingSha256);
    if (path == null ||
        path.isEmpty ||
        version == null ||
        version.isEmpty ||
        size == null ||
        size <= 0 ||
        sha == null ||
        !RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(sha)) {
      return null;
    }

    UpdateManifest? manifest;
    final rawManifest = _linuxPreferences.getString(_prefPendingManifest);
    if (rawManifest != null && rawManifest.isNotEmpty) {
      try {
        manifest = UpdateManifest.fromJson(
          jsonDecode(rawManifest) as Map<String, dynamic>,
        );
      } catch (_) {
        manifest = null;
      }
    }
    return _PendingLinuxInstaller(
      path: path,
      version: version,
      sizeBytes: size,
      sha256: sha.toLowerCase(),
      manifest: manifest,
    );
  }

  Future<void> _clearPendingInstaller({required bool deleteFile}) async {
    final path = _linuxPreferences.getString(_prefPendingPath);
    if (deleteFile && path != null && path.isNotEmpty) {
      try {
        final file = File(path);
        if (await file.exists()) await file.delete();
        final partial = File('$path.part');
        if (await partial.exists()) await partial.delete();
      } catch (_) {
        // Best-effort cleanup; preference state must still be cleared.
      }
    }
    await _linuxPreferences.remove(_prefPendingPath);
    await _linuxPreferences.remove(_prefPendingVersion);
    await _linuxPreferences.remove(_prefPendingSize);
    await _linuxPreferences.remove(_prefPendingSha256);
    await _linuxPreferences.remove(_prefPendingManifest);
  }

  Future<void> _cleanupObsoleteLinuxDownloads({
    required Directory root,
    required String activeVersionKey,
  }) async {
    final linuxRoot = Directory(
      p.join(root.path, _updatesDirectoryName, _linuxDirectoryName),
    );
    if (!await linuxRoot.exists()) return;
    await for (final entity in linuxRoot.list()) {
      if (entity is! Directory || p.basename(entity.path) == activeVersionKey) {
        continue;
      }
      try {
        await entity.delete(recursive: true);
      } catch (_) {
        // Best-effort cleanup only.
      }
    }
  }

  String _sanitizeVersionForPath(String version) => version
      .trim()
      .replaceAll(RegExp(r'[^0-9A-Za-z._-]+'), '_')
      .replaceAll(RegExp(r'_+'), '_');

  void _setError(String message) {
    state.value = state.value.copyWith(
      status: UpdateStatus.error,
      errorMessage: message,
      diagnostics: state.value.diagnostics.copyWith(
        installerLaunchSuccess: false,
        lastException: message,
      ),
    );
  }
}

class _PendingLinuxInstaller {
  const _PendingLinuxInstaller({
    required this.path,
    required this.version,
    required this.sizeBytes,
    required this.sha256,
    required this.manifest,
  });

  final String path;
  final String version;
  final int sizeBytes;
  final String sha256;
  final UpdateManifest? manifest;
}
