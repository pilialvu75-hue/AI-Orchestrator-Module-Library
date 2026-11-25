import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/windows_update_installer.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

/// Windows-specific facade for the existing updater API.
///
/// The UI can keep talking to [UpdateManager]. Android receives the original
/// implementation, while Windows receives this subtype. Discovery/state logic
/// remains shared; only package download, verification, persistence and launch
/// are specialized for the signed Setup.exe flow.
class WindowsUpdateManager extends UpdateManager {
  WindowsUpdateManager({
    required UpdateChecker updateChecker,
    required VersionComparator comparator,
    required SharedPreferences preferences,
    required AndroidIntentHandler intentHandler,
    required String currentVersion,
    WindowsUpdateInstallerPort? windowsInstaller,
    Future<Directory> Function()? temporaryDirectoryProvider,
    Dio? dio,
  })  : _windowsComparator = comparator,
        _windowsPreferences = preferences,
        _windowsCurrentVersion =
            comparator.normalize(currentVersion) ?? currentVersion,
        _windowsInstaller = windowsInstaller ?? WindowsUpdateInstaller(dio: dio),
        _temporaryDirectoryProvider =
            temporaryDirectoryProvider ?? getTemporaryDirectory,
        super(
          updateChecker: updateChecker,
          comparator: comparator,
          preferences: preferences,
          intentHandler: intentHandler,
          currentVersion: currentVersion,
          enableWindowsBetaBuildNumberComparison: true,
          dio: dio,
        );

  static const String _prefPendingPath = 'update_windows_pending_path';
  static const String _prefPendingVersion = 'update_windows_pending_version';
  static const String _prefPendingSize = 'update_windows_pending_size';
  static const String _prefPendingSha256 = 'update_windows_pending_sha256';
  static const String _prefPendingManifest = 'update_windows_pending_manifest';
  static const String _updatesDirectoryName = 'app_updates';
  static const String _windowsDirectoryName = 'windows';

  final VersionComparator _windowsComparator;
  final SharedPreferences _windowsPreferences;
  final WindowsUpdateInstallerPort _windowsInstaller;
  final Future<Directory> Function() _temporaryDirectoryProvider;
  final String _windowsCurrentVersion;

  Timer? _windowsPeriodicTimer;
  bool _windowsDownloadInProgress = false;
  bool _windowsInstallInProgress = false;

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
    _windowsPeriodicTimer?.cancel();
    _windowsPeriodicTimer = Timer.periodic(interval, (_) {
      unawaited(checkForUpdates());
    });
  }

  @override
  void stopBackgroundChecks() {
    _windowsPeriodicTimer?.cancel();
    _windowsPeriodicTimer = null;
  }

  @override
  Future<void> checkForUpdates({
    bool allowCachedFallback = true,
  }) async {
    await super.checkForUpdates(allowCachedFallback: allowCachedFallback);
    await _restorePendingInstaller();
  }

  /// Keeps the legacy public method name so existing UI/settings code remains
  /// source compatible while Windows downloads Setup.exe instead of an APK.
  @override
  Future<bool> downloadLatestApk() => _downloadLatestWindowsInstaller();

  /// Keeps the legacy public method name so the existing update dialog can
  /// launch the Windows installer without platform-specific UI branches.
  @override
  Future<bool> prepareInstallIntent() => _prepareWindowsInstall();

  @override
  Future<bool> forceUpdate() async {
    if (_windowsDownloadInProgress || _windowsInstallInProgress) {
      return false;
    }
    await checkForUpdates(allowCachedFallback: false);
    if (!hasDetectedNewerVersion(state.value)) {
      return false;
    }
    final downloaded = await _downloadLatestWindowsInstaller();
    if (!downloaded) return false;
    return _prepareWindowsInstall();
  }

  @override
  Future<bool> openUnknownAppsSettings() async => false;

  @override
  Future<void> refreshDiagnostics() async {
    final path = _windowsPreferences.getString(_prefPendingPath);
    if (path == null || path.isEmpty) return;
    await _restorePendingInstaller();
  }

  Future<bool> _downloadLatestWindowsInstaller() async {
    if (_windowsDownloadInProgress || _windowsInstallInProgress) {
      return false;
    }
    final manifest = state.value.latestManifest;
    final artifact = manifest?.windowsArtifact;
    if (manifest == null || artifact == null) {
      _setError('No verified Windows installer is available for this release.');
      return false;
    }
    final expectedSize = artifact.sizeBytes;
    final expectedSha256 = artifact.sha256;
    if (expectedSize == null || expectedSize <= 0 || expectedSha256 == null) {
      _setError(
        'Windows installer metadata is incomplete: size and SHA-256 are required.',
      );
      return false;
    }

    _windowsDownloadInProgress = true;
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
      final root = await _temporaryDirectoryProvider();
      final versionKey = _sanitizeVersionForPath(manifest.version);
      final directory = Directory(
        p.join(
          root.path,
          _updatesDirectoryName,
          _windowsDirectoryName,
          versionKey,
        ),
      );
      await directory.create(recursive: true);
      await _cleanupObsoleteWindowsDownloads(
        root: root,
        activeVersionKey: versionKey,
      );

      final finalPath = p.join(directory.path, artifact.fileName);
      final partialPath = '$finalPath.part';
      final downloadedPath = await _windowsInstaller.download(
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
      _setError('Windows installer download failed: $error');
      return false;
    } finally {
      _windowsDownloadInProgress = false;
    }
  }

  Future<bool> _prepareWindowsInstall() async {
    if (_windowsInstallInProgress || _windowsDownloadInProgress) {
      return false;
    }
    _windowsInstallInProgress = true;
    try {
      final pending = await _readPendingInstaller();
      if (pending == null) {
        _setError('No verified Windows installer is ready to install.');
        return false;
      }

      final verification = await _windowsInstaller.verify(
        filePath: pending.path,
        expectedSizeBytes: pending.sizeBytes,
        expectedSha256: pending.sha256,
      );
      if (!verification.valid) {
        await _clearPendingInstaller(deleteFile: true);
        _setError(
          'Windows installer failed verification before launch: '
          '${verification.reason}',
        );
        return false;
      }

      final launched = await _windowsInstaller.launch(pending.path);
      if (!launched) {
        _setError('Windows installer could not be launched.');
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
      _setError('Windows installer launch failed: $error');
      return false;
    } finally {
      _windowsInstallInProgress = false;
    }
  }

  Future<void> _restorePendingInstaller() async {
    final pending = await _readPendingInstaller();
    if (pending == null) return;

    // A verified beta build with a higher numeric build code is newer when
    // Beta is selected, even though conventional SemVer ranks stable higher.
    // Reuse the same rule as update discovery to avoid deleting the installer.
    if (compareCandidateToInstalled(pending.version) <= 0) {
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

    final verification = await _windowsInstaller.verify(
      filePath: pending.path,
      expectedSizeBytes: pending.sizeBytes,
      expectedSha256: pending.sha256,
    );
    if (!verification.valid) {
      await _clearPendingInstaller(deleteFile: true);
      return;
    }

    final manifest = pending.manifest ?? state.value.latestManifest;
    if (manifest == null || manifest.windowsArtifact == null) {
      return;
    }
    if (_windowsComparator.compare(pending.version, manifest.version) < 0) {
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
        updateUrl: manifest.windowsArtifact!.url,
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
    await _windowsPreferences.setString(_prefPendingPath, path);
    await _windowsPreferences.setString(_prefPendingVersion, manifest.version);
    await _windowsPreferences.setInt(_prefPendingSize, sizeBytes);
    await _windowsPreferences.setString(_prefPendingSha256, sha256.toLowerCase());
    await _windowsPreferences.setString(
      _prefPendingManifest,
      jsonEncode(manifest.toJson()),
    );
  }

  Future<_PendingWindowsInstaller?> _readPendingInstaller() async {
    final path = _windowsPreferences.getString(_prefPendingPath);
    final version = _windowsPreferences.getString(_prefPendingVersion);
    final size = _windowsPreferences.getInt(_prefPendingSize);
    final sha = _windowsPreferences.getString(_prefPendingSha256);
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
    final rawManifest = _windowsPreferences.getString(_prefPendingManifest);
    if (rawManifest != null && rawManifest.isNotEmpty) {
      try {
        manifest = UpdateManifest.fromJson(
          jsonDecode(rawManifest) as Map<String, dynamic>,
        );
      } catch (_) {
        manifest = null;
      }
    }
    return _PendingWindowsInstaller(
      path: path,
      version: version,
      sizeBytes: size,
      sha256: sha.toLowerCase(),
      manifest: manifest,
    );
  }

  Future<void> _clearPendingInstaller({required bool deleteFile}) async {
    final path = _windowsPreferences.getString(_prefPendingPath);
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
    await _windowsPreferences.remove(_prefPendingPath);
    await _windowsPreferences.remove(_prefPendingVersion);
    await _windowsPreferences.remove(_prefPendingSize);
    await _windowsPreferences.remove(_prefPendingSha256);
    await _windowsPreferences.remove(_prefPendingManifest);
  }

  Future<void> _cleanupObsoleteWindowsDownloads({
    required Directory root,
    required String activeVersionKey,
  }) async {
    final windowsRoot = Directory(
      p.join(root.path, _updatesDirectoryName, _windowsDirectoryName),
    );
    if (!await windowsRoot.exists()) return;
    await for (final entity in windowsRoot.list()) {
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

class _PendingWindowsInstaller {
  const _PendingWindowsInstaller({
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
