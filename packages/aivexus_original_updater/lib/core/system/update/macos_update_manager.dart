import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aivexus_original_updater/core/system/update/macos_update_installer.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

/// macOS-specific facade for the shared updater API.
///
/// Discovery/state logic remains shared with Android and Windows. macOS only
/// specializes DMG download, SHA-256 verification, persistence and launch.
/// The verified DMG is opened for installation; in-place self replacement is
/// deliberately not attempted from the sandboxed application process.
class MacosUpdateManager extends UpdateManager {
  MacosUpdateManager({
    required UpdateChecker updateChecker,
    required VersionComparator comparator,
    required SharedPreferences preferences,
    required AndroidIntentHandler intentHandler,
    required String currentVersion,
    MacosUpdateInstallerPort? macosInstaller,
    Future<Directory> Function()? temporaryDirectoryProvider,
    Dio? dio,
  })  : _macosComparator = comparator,
        _macosPreferences = preferences,
        _macosCurrentVersion =
            comparator.normalize(currentVersion) ?? currentVersion,
        _macosInstaller = macosInstaller ?? MacosUpdateInstaller(dio: dio),
        _temporaryDirectoryProvider =
            temporaryDirectoryProvider ?? getTemporaryDirectory,
        super(
          updateChecker: updateChecker,
          comparator: comparator,
          preferences: preferences,
          intentHandler: intentHandler,
          currentVersion: currentVersion,
          dio: dio,
        );

  static const String _prefPendingPath = 'update_macos_pending_path';
  static const String _prefPendingVersion = 'update_macos_pending_version';
  static const String _prefPendingSize = 'update_macos_pending_size';
  static const String _prefPendingSha256 = 'update_macos_pending_sha256';
  static const String _prefPendingManifest = 'update_macos_pending_manifest';
  static const String _updatesDirectoryName = 'app_updates';
  static const String _macosDirectoryName = 'macos';

  final VersionComparator _macosComparator;
  final SharedPreferences _macosPreferences;
  final MacosUpdateInstallerPort _macosInstaller;
  final Future<Directory> Function() _temporaryDirectoryProvider;
  final String _macosCurrentVersion;

  Timer? _macosPeriodicTimer;
  bool _macosDownloadInProgress = false;
  bool _macosInstallInProgress = false;

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
    _macosPeriodicTimer?.cancel();
    _macosPeriodicTimer = Timer.periodic(interval, (_) {
      unawaited(checkForUpdates());
    });
  }

  @override
  void stopBackgroundChecks() {
    _macosPeriodicTimer?.cancel();
    _macosPeriodicTimer = null;
  }

  @override
  Future<void> checkForUpdates({
    bool allowCachedFallback = true,
  }) async {
    await super.checkForUpdates(allowCachedFallback: allowCachedFallback);
    await _restorePendingInstaller();
  }

  /// Keeps the legacy method name so existing UI/settings code remains source
  /// compatible while macOS downloads a DMG instead of an APK.
  @override
  Future<bool> downloadLatestApk() => _downloadLatestMacosInstaller();

  /// Keeps the legacy public method name so the existing update dialog can
  /// open the verified DMG without platform-specific UI branches.
  @override
  Future<bool> prepareInstallIntent() => _prepareMacosInstall();

  @override
  Future<bool> forceUpdate() async {
    if (_macosDownloadInProgress || _macosInstallInProgress) {
      return false;
    }
    await checkForUpdates(allowCachedFallback: false);
    if (!hasDetectedNewerVersion(state.value)) {
      return false;
    }
    final downloaded = await _downloadLatestMacosInstaller();
    if (!downloaded) return false;
    return _prepareMacosInstall();
  }

  @override
  Future<bool> openUnknownAppsSettings() async => false;

  @override
  Future<void> refreshDiagnostics() async {
    final path = _macosPreferences.getString(_prefPendingPath);
    if (path == null || path.isEmpty) return;
    await _restorePendingInstaller();
  }

  Future<bool> _downloadLatestMacosInstaller() async {
    if (_macosDownloadInProgress || _macosInstallInProgress) {
      return false;
    }
    final manifest = state.value.latestManifest;
    final artifact = manifest?.macosArtifact;
    if (manifest == null || artifact == null) {
      _setError('No verified macOS installer is available for this release.');
      return false;
    }
    final expectedSize = artifact.sizeBytes;
    final expectedSha256 = artifact.sha256;
    if (expectedSize == null || expectedSize <= 0 || expectedSha256 == null) {
      _setError(
        'macOS installer metadata is incomplete: size and SHA-256 are required.',
      );
      return false;
    }

    _macosDownloadInProgress = true;
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
          _macosDirectoryName,
          versionKey,
        ),
      );
      await directory.create(recursive: true);
      await _cleanupObsoleteMacosDownloads(
        root: root,
        activeVersionKey: versionKey,
      );

      final finalPath = p.join(directory.path, artifact.fileName);
      final partialPath = '$finalPath.part';
      final downloadedPath = await _macosInstaller.download(
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
      _setError('macOS installer download failed: $error');
      return false;
    } finally {
      _macosDownloadInProgress = false;
    }
  }

  Future<bool> _prepareMacosInstall() async {
    if (_macosInstallInProgress || _macosDownloadInProgress) {
      return false;
    }
    _macosInstallInProgress = true;
    try {
      final pending = await _readPendingInstaller();
      if (pending == null) {
        _setError('No verified macOS installer is ready to install.');
        return false;
      }

      final verification = await _macosInstaller.verify(
        filePath: pending.path,
        expectedSizeBytes: pending.sizeBytes,
        expectedSha256: pending.sha256,
      );
      if (!verification.valid) {
        await _clearPendingInstaller(deleteFile: true);
        _setError(
          'macOS installer failed verification before launch: '
          '${verification.reason}',
        );
        return false;
      }

      final launched = await _macosInstaller.launch(pending.path);
      if (!launched) {
        _setError('macOS installer could not be opened.');
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
      _setError('macOS installer launch failed: $error');
      return false;
    } finally {
      _macosInstallInProgress = false;
    }
  }

  Future<void> _restorePendingInstaller() async {
    final pending = await _readPendingInstaller();
    if (pending == null) return;

    if (_macosComparator.compare(_macosCurrentVersion, pending.version) >= 0) {
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

    final verification = await _macosInstaller.verify(
      filePath: pending.path,
      expectedSizeBytes: pending.sizeBytes,
      expectedSha256: pending.sha256,
    );
    if (!verification.valid) {
      await _clearPendingInstaller(deleteFile: true);
      return;
    }

    final manifest = pending.manifest ?? state.value.latestManifest;
    if (manifest == null || manifest.macosArtifact == null) {
      return;
    }
    if (_macosComparator.compare(pending.version, manifest.version) < 0) {
      await _clearPendingInstaller(deleteFile: true);
      return;
    }

    final artifact = manifest.macosArtifact!;
    state.value = state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      latestManifest: manifest,
      tempApkPath: pending.path,
      downloadProgress: 1,
      clearErrorMessage: true,
      diagnostics: state.value.diagnostics.copyWith(
        remoteVersion: manifest.version,
        remoteVersionCode: manifest.versionCode,
        updateUrl: artifact.url,
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
    await _macosPreferences.setString(_prefPendingPath, path);
    await _macosPreferences.setString(_prefPendingVersion, manifest.version);
    await _macosPreferences.setInt(_prefPendingSize, sizeBytes);
    await _macosPreferences.setString(
      _prefPendingSha256,
      sha256.toLowerCase(),
    );
    await _macosPreferences.setString(
      _prefPendingManifest,
      jsonEncode(manifest.toJson()),
    );
  }

  Future<_PendingMacosInstaller?> _readPendingInstaller() async {
    final path = _macosPreferences.getString(_prefPendingPath);
    final version = _macosPreferences.getString(_prefPendingVersion);
    final size = _macosPreferences.getInt(_prefPendingSize);
    final sha = _macosPreferences.getString(_prefPendingSha256);
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
    final rawManifest = _macosPreferences.getString(_prefPendingManifest);
    if (rawManifest != null && rawManifest.isNotEmpty) {
      try {
        manifest = UpdateManifest.fromJson(
          jsonDecode(rawManifest) as Map<String, dynamic>,
        );
      } catch (_) {
        manifest = null;
      }
    }
    return _PendingMacosInstaller(
      path: path,
      version: version,
      sizeBytes: size,
      sha256: sha.toLowerCase(),
      manifest: manifest,
    );
  }

  Future<void> _clearPendingInstaller({required bool deleteFile}) async {
    final path = _macosPreferences.getString(_prefPendingPath);
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
    await _macosPreferences.remove(_prefPendingPath);
    await _macosPreferences.remove(_prefPendingVersion);
    await _macosPreferences.remove(_prefPendingSize);
    await _macosPreferences.remove(_prefPendingSha256);
    await _macosPreferences.remove(_prefPendingManifest);
  }

  Future<void> _cleanupObsoleteMacosDownloads({
    required Directory root,
    required String activeVersionKey,
  }) async {
    final macosRoot = Directory(
      p.join(root.path, _updatesDirectoryName, _macosDirectoryName),
    );
    if (!await macosRoot.exists()) return;
    await for (final entity in macosRoot.list()) {
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

class _PendingMacosInstaller {
  const _PendingMacosInstaller({
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
