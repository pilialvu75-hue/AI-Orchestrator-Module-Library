import 'dart:convert';
import 'package:aivexus_original_updater/core/system/background_download.dart';
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:aivexus_original_updater/core/config/app/app_constants.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

class _ApkVerificationResult {
  const _ApkVerificationResult({
    required this.valid,
    required this.exists,
    required this.readable,
    required this.hasApkExtension,
    required this.sizeBytes,
    required this.reason,
    this.packageName,
    this.versionName,
    this.versionCode,
    this.signatureSha256,
    this.fileSha256,
    this.hasSplitConfig,
    this.abi,
    this.archiveParsed = false,
  });

  final bool valid;
  final bool exists;
  final bool readable;
  final bool hasApkExtension;
  final int sizeBytes;
  final String reason;
  final String? packageName;
  final String? versionName;
  final int? versionCode;
  final String? signatureSha256;
  final String? fileSha256;
  final bool? hasSplitConfig;
  final String? abi;
  final bool archiveParsed;
}

class _InstalledIdentity {
  const _InstalledIdentity({
    required this.versionName,
    required this.versionCode,
    required this.applicationId,
    this.installerPackage,
    this.signatureSha256,
  });

  final String versionName;
  final int? versionCode;
  final String applicationId;
  final String? installerPackage;
  final String? signatureSha256;
}

class UpdateManager {
  static const String _prefApprovedDownload = 'update_approved_background_manifest';
  static const String _prefPendingApkPath = 'update_pending_apk_path';
  static const String _prefPendingVersion = 'update_pending_version';
  static const String _prefPendingSavedAt = 'update_pending_saved_at';
  static const String _prefDownloadPartialPath = 'update_download_partial_path';
  static const String _prefDownloadVersion = 'update_download_version';
  static const String _prefDownloadProgress = 'update_download_progress';
  static const String _prefDownloadReceivedBytes =
      'update_download_received_bytes';
  static const String _prefDownloadTotalBytes = 'update_download_total_bytes';
  static const int _minValidApkBytes = 64 * 1024;
  static const Duration _downloadTimeout = Duration(minutes: 10);
  static const Duration _postInstallVerifyPollInterval = Duration(seconds: 2);
  static const int _postInstallVerifyMaxAttempts = 5;
  static const String _updatesDirectoryName = 'app_updates';
  static const String _defaultApkFileName = 'ai_orchestrator_update.apk';

  UpdateManager({
    required UpdateChecker updateChecker,
    required VersionComparator comparator,
    required SharedPreferences preferences,
    required AndroidIntentHandler intentHandler,
    required String currentVersion,
    bool? allowDebugSignatureMismatchBypass,
    bool enableAndroidBetaBuildNumberComparison = false,
    bool enableWindowsBetaBuildNumberComparison = false,
    Dio? dio,
  })  : _updateChecker = updateChecker,
        _comparator = comparator,
        _preferences = preferences,
        _intentHandler = intentHandler,
        _currentVersion = comparator.normalize(currentVersion) ?? currentVersion,
        _allowDebugSignatureMismatchBypass =
            allowDebugSignatureMismatchBypass ?? kDebugMode,
        _enableAndroidBetaBuildNumberComparison =
            enableAndroidBetaBuildNumberComparison,
        _enableWindowsBetaBuildNumberComparison =
            enableWindowsBetaBuildNumberComparison,
        _dio = dio ?? Dio(),
        state = ValueNotifier<UpdateState>(
          UpdateState.initial(
            currentVersion: comparator.normalize(currentVersion) ?? currentVersion,
            preferredChannel: ReleaseChannel.fromString(
              preferences.getString(AppConstants.prefReleaseChannel),
            ),
          ),
        );

  final UpdateChecker _updateChecker;
  final VersionComparator _comparator;
  final SharedPreferences _preferences;
  final AndroidIntentHandler _intentHandler;
  final String _currentVersion;
  final bool _allowDebugSignatureMismatchBypass;
  final bool _enableAndroidBetaBuildNumberComparison;
  final bool _enableWindowsBetaBuildNumberComparison;
  final Dio _dio;

  final ValueNotifier<UpdateState> state;

  Timer? _periodicTimer;
  // These guards prevent concurrent update operations and race conditions from async UI actions.
  bool _isCheckingForUpdates = false;
  bool _isPreparingInstall = false;

  Future<void> startBackgroundChecks({
    bool checkOnStartup = true,
    Duration interval = const Duration(hours: 12),
  }) async {
    await _resumePendingInstallerState();
    final resumed = await _resumeApprovedDownload();
    if (!resumed && checkOnStartup && state.value.status != UpdateStatus.readyToInstall) {
      unawaited(checkForUpdates());
    }

    _periodicTimer?.cancel();
    _periodicTimer = Timer.periodic(interval, (_) {
      unawaited(checkForUpdates());
    });
  }

  void stopBackgroundChecks() {
    _periodicTimer?.cancel();
    _periodicTimer = null;
  }

  Future<void> setPreferredChannel(ReleaseChannel channel) async {
    await _preferences.setString(
      AppConstants.prefReleaseChannel,
      channel.storageValue,
    );
    state.value = state.value.copyWith(preferredChannel: channel);
    unawaited(checkForUpdates());
  }

  Future<void> checkForUpdates({
    bool allowCachedFallback = true,
  }) async {
    final selectedChannel = state.value.preferredChannel;
    _logStructuredUpdateCheck(
      selectedChannel: selectedChannel,
      finalDecisionState: 'request_received',
    );
    if (_isCheckingForUpdates) {
      _logStructuredUpdateCheck(
        selectedChannel: selectedChannel,
        finalDecisionState: 'skipped_already_checking',
      );
      return;
    }
    if (state.value.status == UpdateStatus.downloading) {
      _logStructuredUpdateCheck(
        selectedChannel: selectedChannel,
        detectedVersion: state.value.latestManifest?.version,
        comparisonResult: _comparisonResultFor(state.value.latestManifest?.version),
        finalDecisionState: 'skipped_downloading',
      );
      return;
    }
    if (_isPreparingInstall) {
      _logStructuredUpdateCheck(
        selectedChannel: selectedChannel,
        detectedVersion: state.value.latestManifest?.version,
        comparisonResult: _comparisonResultFor(state.value.latestManifest?.version),
        finalDecisionState: 'skipped_install_in_progress',
      );
      return;
    }

    _isCheckingForUpdates = true;
    try {
      await _invalidateStalePersistedState();
      _logVersionLocal('version=$_currentVersion');
      state.value = state.value.copyWith(
        status: UpdateStatus.checking,
        clearErrorMessage: true,
      );

      final result = await _updateChecker.checkLatestManifest(
        preferredChannel: selectedChannel,
        allowCachedFallback: allowCachedFallback,
      );

      final manifest = result.manifest;
      if (manifest == null) {
        final message = result.errorMessage ?? 'Update check failed';
        _logUpdateCheck('check_fail error=$message');
        _logStructuredUpdateError(
          action: 'check_for_updates',
          selectedChannel: selectedChannel,
          finalDecisionState: 'error',
          message: message,
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: message,
          lastCheckedAt: DateTime.now(),
          diagnostics: state.value.diagnostics.copyWith(
            lastException: message,
          ),
        );
        return;
      }

      final compareResult = _compareCandidateToInstalled(manifest.version);
      final compatible = manifest.isCompatibleWith(
        currentVersion: _currentVersion,
        comparator: _comparator,
      );
      await _logReleaseForensicsCheck(manifest);
      _logVersionRemote(
        'version=${manifest.version} versionCode=${manifest.versionCode ?? '-'} url=${manifest.apkUrl}',
      );
      _logStructuredVersionCompare(
        detectedVersion: manifest.version,
        selectedChannel: selectedChannel,
        comparisonResult: compareResult,
        compatible: compatible,
        finalDecisionState: compatible
            ? (compareResult > 0 ? 'candidate_update' : 'up_to_date')
            : 'blocked_by_min_supported',
      );

      if (!compatible) {
        state.value = state.value.copyWith(
          status: UpdateStatus.upToDate,
          latestManifest: manifest,
          lastCheckedAt: DateTime.now(),
          usedCachedManifest: result.usedCache,
          clearErrorMessage: true,
          clearTempApkPath: true,
          downloadProgress: 0,
          diagnostics: state.value.diagnostics.copyWith(
            remoteVersion: manifest.version,
            remoteVersionCode: manifest.versionCode,
            updateUrl: manifest.apkUrl,
            apkDownloaded: false,
            clearApkPath: true,
            apkFileExists: false,
            clearInstallerLaunchSuccess: true,
            clearLastException: true,
          ),
        );
        _logStructuredUpdateCheck(
          selectedChannel: selectedChannel,
          detectedVersion: manifest.version,
          comparisonResult: compareResult,
          finalDecisionState: 'up_to_date',
        );
        return;
      }

      if (compareResult > 0 &&
          await _restoreReadyToInstallStateIfReusable(
            manifest: manifest,
            selectedChannel: selectedChannel,
            comparisonResult: compareResult,
            usedCachedManifest: result.usedCache,
          )) {
        return;
      }

      state.value = state.value.copyWith(
        status: compareResult > 0
            ? UpdateStatus.updateAvailable
            : UpdateStatus.upToDate,
        latestManifest: manifest,
        lastCheckedAt: DateTime.now(),
        usedCachedManifest: result.usedCache,
        clearErrorMessage: true,
        clearTempApkPath: true,
        downloadProgress: 0,
        diagnostics: state.value.diagnostics.copyWith(
          remoteVersion: manifest.version,
          remoteVersionCode: manifest.versionCode,
          updateUrl: manifest.apkUrl,
          apkDownloaded: false,
          clearApkPath: true,
          apkFileExists: false,
          clearInstallerLaunchSuccess: true,
          clearLastException: true,
        ),
      );
      if (compareResult > 0) {
        _logStructuredUpdateAvailable(
          detectedVersion: manifest.version,
          selectedChannel: selectedChannel,
          comparisonResult: compareResult,
          finalDecisionState: 'update_available',
        );
      }
      _logStructuredUpdateCheck(
        selectedChannel: selectedChannel,
        detectedVersion: manifest.version,
        comparisonResult: compareResult,
        finalDecisionState: compareResult > 0 ? 'update_available' : 'up_to_date',
      );
    } finally {
      _isCheckingForUpdates = false;
    }
  }

  Future<bool> downloadLatestApk() async {
    final manifest = state.value.latestManifest;
    if (manifest == null) {
      _logApk('Download requested without latest manifest');
      _logStructuredUpdateError(
        action: 'download_latest_apk',
        selectedChannel: state.value.preferredChannel,
        finalDecisionState: state.value.status.name,
        message: 'No latest manifest available',
      );
      return false;
    }
    if (state.value.status == UpdateStatus.downloading) {
      _logStructuredDownloadTrigger(
        detectedVersion: manifest.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _compareCandidateToInstalled(manifest.version),
        finalDecisionState: 'skipped_downloading',
      );
      return false;
    }
    if (_isPreparingInstall) {
      _logStructuredDownloadTrigger(
        detectedVersion: manifest.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _compareCandidateToInstalled(manifest.version),
        finalDecisionState: 'skipped_install_in_progress',
      );
      return false;
    }
    _logStructuredDownloadTrigger(
      detectedVersion: manifest.version,
      selectedChannel: state.value.preferredChannel,
      comparisonResult: _compareCandidateToInstalled(manifest.version),
      finalDecisionState: 'download_requested',
    );
    _logUpdateDownload(
      'release_tag=${manifest.version} '
      'apk_filename=${manifest.apkFileName ?? '-'} '
      'apk_size_bytes=${manifest.apkSizeBytes ?? -1} '
      'apk_url=${manifest.apkUrl}',
    );

    final uri = Uri.tryParse(manifest.apkUrl);
    if (uri == null ||
        !(uri.scheme == 'https' || uri.scheme == 'http') ||
        uri.host.isEmpty) {
      _logApk('Rejected invalid APK URL: ${manifest.apkUrl}');
      _logStructuredUpdateError(
        action: 'download_latest_apk',
        detectedVersion: manifest.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _compareCandidateToInstalled(manifest.version),
        finalDecisionState: 'error',
        message: 'Invalid APK URL: ${manifest.apkUrl}',
      );
      state.value = state.value.copyWith(
        status: UpdateStatus.error,
        errorMessage:
            'Previously validated APK URL is now invalid: ${manifest.apkUrl}',
        diagnostics: state.value.diagnostics.copyWith(
          lastException: 'Invalid APK URL: ${manifest.apkUrl}',
        ),
      );
      return false;
    }

    await _cleanupObsoleteDownloadedApks(activeVersion: manifest.version);
    final updatesDirectory = await _ensureVersionScopedUpdateDirectory(
      manifest.version,
    );
    final fileName = _resolveApkFileName(manifest, uri);
    final finalPath = p.join(updatesDirectory.path, fileName);
    final partialPath = '$finalPath.part';
    var activePath = partialPath;

    state.value = state.value.copyWith(
      status: UpdateStatus.downloading,
      downloadProgress: 0,
      clearErrorMessage: true,
      clearTempApkPath: true,
      diagnostics: state.value.diagnostics.copyWith(
        updateUrl: manifest.apkUrl,
        apkDownloaded: false,
        clearApkPath: true,
        apkFileExists: false,
        clearInstallerLaunchSuccess: true,
        clearLastException: true,
      ),
    );

    try {
      final finalFile = File(finalPath);
      if (await finalFile.exists()) {
        final verified = await _verifyApkFile(
          finalPath,
          expectedSizeBytes: manifest.apkSizeBytes,
        );
        if (verified.valid) {
          _logUpdateApkReady(
            'release_tag=${manifest.version} '
            'apk_filename=${p.basename(finalPath)} '
            'apk_size_bytes=${verified.sizeBytes} '
            'target_application_id=${verified.packageName ?? '-'} '
            'target_version_name=${verified.versionName ?? '-'} '
            'target_version_code=${verified.versionCode?.toString() ?? '-'} '
            'sha256=${verified.fileSha256 ?? '-'}',
          );
          _logUpdateApkAnalysis(
            'apk_filename=${p.basename(finalPath)} '
            'abi=${verified.abi ?? '-'} '
            'split_config_present=${verified.hasSplitConfig ?? false} '
            'package_archive_info=${verified.archiveParsed}',
          );
          _logUpdateDownloadComplete(
            'reuse_existing path=$finalPath size_bytes=${verified.sizeBytes}',
          );
          _logStructuredDownloadTrigger(
            detectedVersion: manifest.version,
            selectedChannel: state.value.preferredChannel,
            comparisonResult: _compareCandidateToInstalled(manifest.version),
            finalDecisionState: 'ready_to_install',
          );
          await _clearDownloadState();
          await _persistPendingInstallerState(
            apkPath: finalPath,
            version: manifest.version,
          );
          state.value = state.value.copyWith(
            status: UpdateStatus.readyToInstall,
            tempApkPath: finalPath,
            downloadProgress: 1,
            diagnostics: state.value.diagnostics.copyWith(
              apkDownloaded: true,
              apkPath: finalPath,
              apkFileExists: true,
              clearLastException: true,
            ),
          );
          return true;
        }
        await _cleanupInstallerArtifacts(finalPath);
      }

      final partialFile = File(partialPath);
      final existingPartialBytes =
          await partialFile.exists() ? await partialFile.length() : 0;
      await _persistDownloadState(
        partialPath: partialPath,
        version: manifest.version,
        progress: 0,
        receivedBytes: existingPartialBytes,
        totalBytes: manifest.apkSizeBytes,
      );
      _logUpdateDownloadStart(
        'url=${manifest.apkUrl} path=$partialPath resume_bytes=$existingPartialBytes',
      );
      if (Platform.isAndroid) {
        await _preferences.setString(_prefApprovedDownload, jsonEncode(manifest.toJson()));
      }
      await _downloadApkToPartialFile(
        manifest: manifest,
        partialFile: partialFile,
        existingPartialBytes: existingPartialBytes,
      );

      if (await finalFile.exists()) {
        await finalFile.delete();
      }
      await partialFile.rename(finalPath);
      activePath = finalPath;

      final verification = await _verifyApkFile(
        finalPath,
        expectedSizeBytes: manifest.apkSizeBytes,
      );
      if (!verification.valid) {
        if (Platform.isAndroid) await BackgroundDownload.release(manifest.apkUrl);
        await _cleanupInstallerArtifacts(finalPath);
        await _clearDownloadState();
        _logUpdateDownloadFail(
          'reason=${verification.reason} path=$finalPath size_bytes=${verification.sizeBytes}',
        );
        _logStructuredUpdateError(
          action: 'download_latest_apk',
          detectedVersion: manifest.version,
          selectedChannel: state.value.preferredChannel,
          comparisonResult: _compareCandidateToInstalled(manifest.version),
          finalDecisionState: 'error',
          message: 'Downloaded APK failed verification: ${verification.reason}',
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: 'Downloaded APK failed verification: ${verification.reason}',
          diagnostics: state.value.diagnostics.copyWith(
            apkDownloaded: false,
            apkPath: finalPath,
            apkFileExists: verification.exists,
            lastException: 'APK verification failed: ${verification.reason}',
          ),
        );
        return false;
      }
      _logUpdateApkReady(
        'release_tag=${manifest.version} '
        'apk_filename=${p.basename(finalPath)} '
        'apk_size_bytes=${verification.sizeBytes} '
        'target_application_id=${verification.packageName ?? '-'} '
        'target_version_name=${verification.versionName ?? '-'} '
        'target_version_code=${verification.versionCode?.toString() ?? '-'} '
        'sha256=${verification.fileSha256 ?? '-'}',
      );
      _logUpdateApkAnalysis(
        'apk_filename=${p.basename(finalPath)} '
        'abi=${verification.abi ?? '-'} '
        'split_config_present=${verification.hasSplitConfig ?? false} '
        'package_archive_info=${verification.archiveParsed}',
      );

      if (Platform.isAndroid) await BackgroundDownload.release(manifest.apkUrl);
      await _clearDownloadState();
      await _persistPendingInstallerState(
        apkPath: finalPath,
        version: manifest.version,
      );
      _logUpdateDownloadComplete(
        'path=$finalPath size_bytes=${verification.sizeBytes}',
      );
      _logStructuredDownloadTrigger(
        detectedVersion: manifest.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _compareCandidateToInstalled(manifest.version),
        finalDecisionState: 'ready_to_install',
      );
      state.value = state.value.copyWith(
        status: UpdateStatus.readyToInstall,
        tempApkPath: finalPath,
        downloadProgress: 1,
        diagnostics: state.value.diagnostics.copyWith(
          apkDownloaded: true,
          apkPath: finalPath,
          apkFileExists: true,
          clearLastException: true,
        ),
      );
      return true;
    } catch (error, stackTrace) {
      _logUpdateDownloadFail('error=$error path=$activePath');
      _logApk('Download failed: $error');
      _logApk('Download stack: $stackTrace');
      _logStructuredUpdateError(
        action: 'download_latest_apk',
        detectedVersion: manifest.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _compareCandidateToInstalled(manifest.version),
        finalDecisionState: 'error',
        message: 'Download failed: $error',
      );
      state.value = state.value.copyWith(
        status: UpdateStatus.error,
        errorMessage: 'Download failed: $error',
        diagnostics: state.value.diagnostics.copyWith(
          apkDownloaded: false,
          apkPath: activePath,
          apkFileExists: await File(activePath).exists(),
          lastException: 'Download failed: $error',
        ),
      );
      return false;
    }
  }

  Future<bool> prepareInstallIntent() async {
    if (_isPreparingInstall) {
      _logStructuredInstallTrigger(
        detectedVersion: state.value.latestManifest?.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _comparisonResultFor(state.value.latestManifest?.version),
        finalDecisionState: 'skipped_install_in_progress',
      );
      return false;
    }
    _isPreparingInstall = true;
    _logUpdateInstallStart();
    try {
      await _syncAndroidInstallDiagnostics();
      final apkPath = state.value.tempApkPath;
      final detectedVersion = state.value.latestManifest?.version ??
          _preferences.getString(_prefPendingVersion);
      final comparisonResult = _comparisonResultFor(detectedVersion);
      final installedIdentity = await _readInstalledIdentity();
      if (apkPath == null || apkPath.isEmpty) {
        _logUpdateInstallFail('No downloaded APK available');
        _logInstall('Install requested without downloaded APK');
        _logStructuredUpdateError(
          action: 'prepare_install_intent',
          detectedVersion: detectedVersion,
          selectedChannel: state.value.preferredChannel,
          comparisonResult: comparisonResult,
          finalDecisionState: 'error',
          message: 'No downloaded APK available',
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: 'No downloaded APK available',
          diagnostics: state.value.diagnostics.copyWith(
            lastException: 'No downloaded APK available',
            installerLaunchSuccess: false,
          ),
        );
        return false;
      }

      _logStructuredInstallTrigger(
        detectedVersion: detectedVersion,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: comparisonResult,
        finalDecisionState: 'install_requested',
      );
      _logUpdateInstallBegin(
        'application_id=${installedIdentity.applicationId} '
        'installed_version_name=${installedIdentity.versionName} '
        'installed_version_code=${installedIdentity.versionCode?.toString() ?? '-'} '
        'installer_package=${installedIdentity.installerPackage ?? '-'} '
        'release_tag=${detectedVersion ?? '-'} '
        'apk_filename=${p.basename(apkPath)}',
      );

      final verification = await _verifyApkFile(
        apkPath,
        expectedSizeBytes: state.value.latestManifest?.apkSizeBytes,
      );
      if (!verification.valid) {
        _logUpdateInstallFail(verification.reason);
        _logStructuredUpdateError(
          action: 'prepare_install_intent',
          detectedVersion: detectedVersion,
          selectedChannel: state.value.preferredChannel,
          comparisonResult: comparisonResult,
          finalDecisionState: 'error',
          message: 'Downloaded APK is no longer valid: ${verification.reason}',
        );
        await _cleanupInstallerArtifacts(apkPath);
        await _clearPendingInstallerState();
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          clearTempApkPath: true,
          errorMessage: 'Downloaded APK is no longer valid: ${verification.reason}',
          diagnostics: state.value.diagnostics.copyWith(
            apkDownloaded: false,
            apkPath: apkPath,
            apkFileExists: verification.exists,
            installerLaunchSuccess: false,
            lastException: 'APK invalid before install: ${verification.reason}',
          ),
        );
        return false;
      }
      _logUpdateApkAnalysis(
        'apk_filename=${p.basename(apkPath)} '
        'abi=${verification.abi ?? '-'} '
        'split_config_present=${verification.hasSplitConfig ?? false} '
        'package_archive_info=${verification.archiveParsed}',
      );
      _logSignatureCurrent(
        'application_id=${installedIdentity.applicationId} sha256=${installedIdentity.signatureSha256 ?? '-'}',
      );
      _logSignatureNew(
        'apk_filename=${p.basename(apkPath)} '
        'application_id=${verification.packageName ?? '-'} '
        'sha256=${verification.signatureSha256 ?? '-'}',
      );
      if (verification.hasSplitConfig == true) {
        const message = 'Split APK artifact is not supported by current installer flow';
        _logStructuredUpdateError(
          action: 'prepare_install_intent',
          detectedVersion: detectedVersion,
          selectedChannel: state.value.preferredChannel,
          comparisonResult: comparisonResult,
          finalDecisionState: 'error',
          message: message,
        );
        _logUpdateInstallResult(
          'success=false reason=split_apk_unsupported apk_path=$apkPath',
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: message,
          diagnostics: state.value.diagnostics.copyWith(
            installerLaunchSuccess: false,
            apkPath: apkPath,
            apkFileExists: verification.exists,
            lastException: message,
          ),
        );
        return false;
      }

      final targetVersionCode =
          verification.versionCode ?? state.value.latestManifest?.versionCode;
      final installedVersionCode = installedIdentity.versionCode;
      if (targetVersionCode != null &&
          installedVersionCode != null &&
          targetVersionCode <= installedVersionCode) {
        _logVersionRejected(
          'installed_version_code=$installedVersionCode '
          'target_version_code=$targetVersionCode '
          'release_tag=${detectedVersion ?? '-'} '
          'apk_filename=${p.basename(apkPath)}',
        );
        final message =
            'Rejected update because APK versionCode ($targetVersionCode) <= installed versionCode ($installedVersionCode)';
        _logUpdateInstallResult(
          'success=false reason=version_code_rejected apk_path=$apkPath',
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: message,
          diagnostics: state.value.diagnostics.copyWith(
            installerLaunchSuccess: false,
            apkPath: apkPath,
            apkFileExists: verification.exists,
            lastException: message,
          ),
        );
        return false;
      }

      final signaturesDiffer =
          installedIdentity.signatureSha256 != null &&
              verification.signatureSha256 != null &&
              installedIdentity.signatureSha256 != verification.signatureSha256;
      if (signaturesDiffer) {
        _logSignatureMismatch(
          'reason=signature_fingerprint_mismatch '
          'current=${installedIdentity.signatureSha256} '
          'new=${verification.signatureSha256}',
        );
        if (_allowDebugSignatureMismatchBypass) {
          const warning = 'Warning: APK signature mismatch bypassed for local development. '
              'Bypass defaults to enabled in debug mode and disabled in release mode unless explicitly overridden.';
          _logInstall(warning);
          _logUpdateInstallResult(
            'success=true reason=signature_mismatch_debug_bypass apk_path=$apkPath',
          );
        } else {
          const message = 'APK signature does not match installed app signature';
          _logUpdateInstallResult(
            'success=false reason=signature_mismatch apk_path=$apkPath',
          );
          state.value = state.value.copyWith(
            status: UpdateStatus.error,
            errorMessage: message,
            diagnostics: state.value.diagnostics.copyWith(
              installerLaunchSuccess: false,
              apkPath: apkPath,
              apkFileExists: verification.exists,
              lastException: message,
            ),
          );
          return false;
        }
      }

      final result = await _intentHandler.openApkInstaller(apkPath);
      if (result.isLeft()) {
        final failure = result.swap().getOrElse(
              () => throw StateError('Unexpected empty failure'),
            );
        _logUpdateInstallFail(failure.message);
        _logInstall('Installer launch failed: ${failure.message}');
        _logUpdateInstallResult(
          'success=false reason=installer_launch_failed message=${failure.message}',
        );
        _logStructuredUpdateError(
          action: 'prepare_install_intent',
          detectedVersion: detectedVersion,
          selectedChannel: state.value.preferredChannel,
          comparisonResult: comparisonResult,
          finalDecisionState: 'error',
          message: failure.message,
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: failure.message,
          diagnostics: state.value.diagnostics.copyWith(
            installerLaunchSuccess: false,
            apkPath: apkPath,
            apkFileExists: true,
            lastException: failure.message,
          ),
        );
        return false;
      }

      final success = result.getOrElse(() => false);
      _logInstall('Installer launch result: success=$success');
      await _syncAndroidInstallDiagnostics();
      if (!success) {
        _logUpdateInstallFail('installer_launch_returned_false');
        _logUpdateInstallResult(
          'success=false reason=installer_launch_returned_false',
        );
        _logStructuredUpdateError(
          action: 'prepare_install_intent',
          detectedVersion: detectedVersion,
          selectedChannel: state.value.preferredChannel,
          comparisonResult: comparisonResult,
          finalDecisionState: 'error',
          message: 'Installer launch failed.',
        );
        state.value = state.value.copyWith(
          status: UpdateStatus.error,
          errorMessage: 'Installer launch failed.',
        );
        return false;
      }

      final persistedVersion = state.value.latestManifest?.version ??
          _preferences.getString(_prefPendingVersion) ??
          _currentVersion;
      await _persistPendingInstallerState(
        apkPath: apkPath,
        version: persistedVersion,
      );
      _logUpdateInstallResume(
        'installer_ready path=$apkPath version=$persistedVersion',
      );
      _logStructuredInstallTrigger(
        detectedVersion: persistedVersion,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _comparisonResultFor(persistedVersion),
        finalDecisionState: 'ready_to_install',
      );
      _logUpdateInstallSuccess();
      _logUpdateInstallResult(
        'success=true launched=true apk_path=$apkPath',
      );
      await _runPostInstallVerification(
        beforeInstallVersionCode: installedVersionCode,
        expectedVersionCode: targetVersionCode,
        expectedVersionName: verification.versionName ??
            state.value.latestManifest?.version,
        releaseTag: persistedVersion,
      );
      state.value = state.value.copyWith(
        status: UpdateStatus.readyToInstall,
        tempApkPath: apkPath,
        downloadProgress: 1,
        diagnostics: state.value.diagnostics.copyWith(
          installerLaunchSuccess: success,
          apkDownloaded: true,
          apkPath: apkPath,
          apkFileExists: true,
          clearLastException: true,
        ),
      );
      return success;
    } finally {
      _isPreparingInstall = false;
    }
  }

  String get currentVersion => _currentVersion;

  bool hasDetectedNewerVersion(UpdateState updateState) {
    final manifest = updateState.latestManifest;
    if (manifest == null) {
      return false;
    }
    return _compareCandidateToInstalled(manifest.version) > 0;
  }

  Future<bool> forceUpdate() async {
    if (state.value.status == UpdateStatus.downloading || _isPreparingInstall) {
      return false;
    }
    await _invalidateStalePersistedState();
    await _updateChecker.clearCachedManifest(
      preferredChannel: state.value.preferredChannel,
    );
    await checkForUpdates(allowCachedFallback: false);
    if (!hasDetectedNewerVersion(state.value)) {
      _logStructuredUpdateError(
        action: 'force_update',
        detectedVersion: state.value.latestManifest?.version,
        selectedChannel: state.value.preferredChannel,
        comparisonResult: _comparisonResultFor(state.value.latestManifest?.version),
        finalDecisionState: state.value.status.name,
        message: 'No newer update detected',
      );
      return false;
    }
    final downloaded = await downloadLatestApk();
    if (!downloaded) {
      return false;
    }
    return prepareInstallIntent();
  }

  Future<bool> openUnknownAppsSettings() async {
    _logInstall('Opening unknown apps permission settings');
    final result = await _intentHandler.openUnknownAppsSettings();
    return result.fold(
      (failure) {
        state.value = state.value.copyWith(
          diagnostics: state.value.diagnostics.copyWith(
            lastException: failure.message,
          ),
        );
        return false;
      },
      (success) => success,
    );
  }

  Future<void> refreshDiagnostics() => _syncAndroidInstallDiagnostics();

  Future<void> _syncAndroidInstallDiagnostics() async {
    final result = await _intentHandler.getInstallDiagnostics();
    result.fold(
      (failure) {
        _logInstall('Diagnostics fetch failed: ${failure.message}');
        state.value = state.value.copyWith(
          diagnostics: state.value.diagnostics.copyWith(
            lastException: state.value.diagnostics.lastException ?? failure.message,
          ),
        );
      },
      (map) {
        _logInstall('Diagnostics payload: $map');
        final sdkInt = map['sdkInt'] is int ? map['sdkInt'] as int : null;
        final canInstall = map['canRequestPackageInstalls'] is bool
            ? map['canRequestPackageInstalls'] as bool
            : null;
        final launchSuccess = map['lastInstallerLaunchSuccess'] is bool
            ? map['lastInstallerLaunchSuccess'] as bool
            : null;
        final lastException = map['lastInstallerException'] is String
            ? map['lastInstallerException'] as String
            : null;
        final resultCode = map['lastInstallerResultCode'] is int
            ? map['lastInstallerResultCode'] as int
            : null;
        state.value = state.value.copyWith(
          diagnostics: state.value.diagnostics.copyWith(
            androidSdkInt: sdkInt,
            canRequestPackageInstalls: canInstall,
            installerLaunchSuccess: launchSuccess,
            lastException: lastException,
            lastInstallerResultCode: resultCode,
            clearAndroidSdkInt: sdkInt == null,
            clearCanRequestPackageInstalls: canInstall == null,
            clearInstallerLaunchSuccess: launchSuccess == null,
            clearLastException: lastException == null,
            clearLastInstallerResultCode: resultCode == null,
          ),
        );
      },
    );
  }

  /// Official Android beta APKs use a plain versionName (1.0.15) and
  /// a separate monotonic versionCode (103459). PackageInfo loses the beta
  /// designation while the GitHub release tag preserves it.
  ///
  /// With explicit beta opt-in, permit only same-base beta upgrades whose
  /// numeric APK build code is strictly greater. Ordinary SemVer ordering and
  /// other platforms remain unchanged; missing codes cannot bypass checks.
  /// A beta-enabled platform may select a newer verified numeric build even
  /// when the installed package version omitted the beta prerelease suffix.
  /// Exposes the same comparison to desktop pending-installer validation.
  @protected
  int compareCandidateToInstalled(String candidateVersion) =>
      _compareCandidateToInstalled(candidateVersion);

  int _compareCandidateToInstalled(String candidateVersion) {
    final conventional = _comparator.compare(candidateVersion, _currentVersion);
    final eligibleAndroid = _enableAndroidBetaBuildNumberComparison &&
        state.value.preferredChannel.allows(ReleaseChannel.beta);
    final eligibleWindows = _enableWindowsBetaBuildNumberComparison &&
        state.value.preferredChannel == ReleaseChannel.beta;
    // Windows package_info exposes the numeric file version, not the Dev
    // prerelease label. Our one-off Win8.1 1.0.16 Dev lab must remain
    // updateable on the *next* authorized Dev build; never extend this
    // exception to ordinary Windows versions or non-Dev channels.
    final eligibleWin81Dev = _enableWindowsBetaBuildNumberComparison &&
        state.value.preferredChannel == ReleaseChannel.dev;
    if (!eligibleAndroid && !eligibleWindows && !eligibleWin81Dev) {
      return conventional;
    }
    final candidate = _comparator.parse(candidateVersion);
    final installed = _comparator.parse(_currentVersion);
    if (candidate == null ||
        installed == null ||
        installed.isPreRelease ||
        candidate.numericSegments.length != 4 ||
        installed.numericSegments.length != 4) {
      return conventional;
    }
    final betaCandidate = candidate.channel == ReleaseChannel.beta &&
        (eligibleAndroid || eligibleWindows);
    final win81DevCandidate = eligibleWin81Dev &&
        candidate.channel == ReleaseChannel.dev &&
        candidate.numericSegments[0] == 1 &&
        candidate.numericSegments[1] == 0 &&
        candidate.numericSegments[2] == 16;
    if (!betaCandidate && !win81DevCandidate) {
      return conventional;
    }
    for (var i = 0; i < 3; i++) {
      if (candidate.numericSegments[i] != installed.numericSegments[i]) {
        return conventional;
      }
    }
    return candidate.numericSegments[3].compareTo(installed.numericSegments[3]);
  }

  int? _comparisonResultFor(String? detectedVersion) {
    if (detectedVersion == null || detectedVersion.trim().isEmpty) {
      return null;
    }
    return _compareCandidateToInstalled(detectedVersion);
  }

  Future<void> _invalidateStalePersistedState({
    bool forceInvalidateMismatched = false,
  }) async {
    final pendingPath = _preferences.getString(_prefPendingApkPath);
    final pendingVersion = _preferences.getString(_prefPendingVersion);
    if (pendingPath != null && pendingPath.trim().isNotEmpty) {
      if (pendingVersion == null || pendingVersion.trim().isEmpty) {
        await _cleanupInstallerArtifacts(pendingPath);
        await _clearPendingInstallerState();
        if (state.value.tempApkPath == pendingPath ||
            state.value.status == UpdateStatus.readyToInstall) {
          state.value = state.value.copyWith(
            status: UpdateStatus.idle,
            clearTempApkPath: true,
            downloadProgress: 0,
          );
        }
      } else {
        final shouldClearPending = forceInvalidateMismatched ||
            _compareCandidateToInstalled(pendingVersion) <= 0;
        if (shouldClearPending) {
          await _cleanupInstallerArtifacts(pendingPath);
          await _clearPendingInstallerState();
          if (state.value.tempApkPath == pendingPath ||
              state.value.status == UpdateStatus.readyToInstall) {
            state.value = state.value.copyWith(
              status: UpdateStatus.idle,
              clearTempApkPath: true,
              downloadProgress: 0,
            );
          }
        } else {
          final verification = await _verifyApkFile(pendingPath);
          if (!verification.valid) {
            await _cleanupInstallerArtifacts(pendingPath);
            await _clearPendingInstallerState();
            if (state.value.tempApkPath == pendingPath ||
                state.value.status == UpdateStatus.readyToInstall) {
              state.value = state.value.copyWith(
                status: UpdateStatus.idle,
                clearTempApkPath: true,
                downloadProgress: 0,
              );
            }
          }
        }
      }
    }

    final partialPath = _preferences.getString(_prefDownloadPartialPath);
    final downloadVersion = _preferences.getString(_prefDownloadVersion);
    if (partialPath == null || partialPath.trim().isEmpty) {
      if (state.value.status == UpdateStatus.downloading) {
        state.value = state.value.copyWith(
          status: UpdateStatus.idle,
          downloadProgress: 0,
        );
      }
      return;
    }

    final partialFile = File(partialPath);
    final partialExists = await partialFile.exists();
    final shouldClearDownload = forceInvalidateMismatched ||
        !partialExists ||
        downloadVersion == null ||
        downloadVersion.trim().isEmpty ||
        _compareCandidateToInstalled(downloadVersion) <= 0;
    if (shouldClearDownload) {
      await _cleanupInstallerArtifacts(partialPath);
      await _clearDownloadState();
      if (state.value.status == UpdateStatus.downloading) {
        state.value = state.value.copyWith(
          status: UpdateStatus.idle,
          downloadProgress: 0,
        );
      }
    }
  }

  Future<bool> _restoreReadyToInstallStateIfReusable({
    required UpdateManifest manifest,
    required ReleaseChannel selectedChannel,
    required int comparisonResult,
    required bool usedCachedManifest,
  }) async {
    final pendingPath = _preferences.getString(_prefPendingApkPath);
    final pendingVersion = _preferences.getString(_prefPendingVersion);
    if (pendingPath == null ||
        pendingPath.trim().isEmpty ||
        pendingVersion == null ||
        pendingVersion.trim().isEmpty) {
      return false;
    }

    if (_compareCandidateToInstalled(pendingVersion) <= 0 ||
        _comparator.compare(pendingVersion, manifest.version) < 0) {
      await _cleanupInstallerArtifacts(pendingPath);
      await _clearPendingInstallerState();
      if (state.value.tempApkPath == pendingPath ||
          state.value.status == UpdateStatus.readyToInstall) {
        state.value = state.value.copyWith(
          status: UpdateStatus.idle,
          clearTempApkPath: true,
          downloadProgress: 0,
        );
      }
      return false;
    }

    final verification = await _verifyApkFile(
      pendingPath,
      expectedSizeBytes: manifest.apkSizeBytes,
    );
    if (!verification.valid) {
      await _cleanupInstallerArtifacts(pendingPath);
      await _clearPendingInstallerState();
      if (state.value.tempApkPath == pendingPath ||
          state.value.status == UpdateStatus.readyToInstall) {
        state.value = state.value.copyWith(
          status: UpdateStatus.idle,
          clearTempApkPath: true,
          downloadProgress: 0,
        );
      }
      return false;
    }

    _logUpdateInstallResume(
      'reuse_pending_download path=$pendingPath version=$pendingVersion',
    );
    _logStructuredUpdateAvailable(
      detectedVersion: manifest.version,
      selectedChannel: selectedChannel,
      comparisonResult: comparisonResult,
      finalDecisionState: 'ready_to_install',
    );
    state.value = state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      latestManifest: manifest,
      lastCheckedAt: DateTime.now(),
      usedCachedManifest: usedCachedManifest,
      tempApkPath: pendingPath,
      downloadProgress: 1,
      clearErrorMessage: true,
      diagnostics: state.value.diagnostics.copyWith(
        remoteVersion: manifest.version,
        remoteVersionCode: manifest.versionCode,
        updateUrl: manifest.apkUrl,
        apkDownloaded: true,
        apkPath: pendingPath,
        apkFileExists: true,
        clearInstallerLaunchSuccess: true,
        clearLastException: true,
      ),
    );
    _logStructuredUpdateCheck(
      selectedChannel: selectedChannel,
      detectedVersion: manifest.version,
      comparisonResult: comparisonResult,
      finalDecisionState: 'ready_to_install',
    );
    return true;
  }

  Future<bool> _resumeApprovedDownload() async {
    if (!Platform.isAndroid || state.value.status == UpdateStatus.readyToInstall) return false;
    final saved = _preferences.getString(_prefApprovedDownload);
    if (saved == null) return false;
    try {
      final manifest = UpdateManifest.fromJson(jsonDecode(saved) as Map<String, dynamic>);
      if (_compareCandidateToInstalled(manifest.version) <= 0) {
        await BackgroundDownload.release(manifest.apkUrl);
        await _preferences.remove(_prefApprovedDownload);
        return false;
      }
      final existing = await BackgroundDownload.channel.invokeMapMethod<String, dynamic>(
        'status', {'url': manifest.apkUrl},
      );
      // Reattach only to a request that was explicitly approved earlier.
      // Removed/failed requests need another tap; never silently restart them.
      if (existing == null || existing['status'] == 16) return false;
      state.value = state.value.copyWith(latestManifest: manifest);
      unawaited(downloadLatestApk());
      return true;
    } catch (error) {
      _logUpdateDownloadFail('background_restore_failed type=${error.runtimeType}');
      return false;
    }
  }

  Future<void> _resumePendingInstallerState() async {
    final pendingPath = _preferences.getString(_prefPendingApkPath);
    if (pendingPath == null || pendingPath.trim().isEmpty) {
      return;
    }

    final pendingVersion = _preferences.getString(_prefPendingVersion);
    if (pendingVersion != null &&
        _compareCandidateToInstalled(pendingVersion) <= 0) {
      _logUpdateInstallCleanup(
        'installed_version_reached current=$_currentVersion pending=$pendingVersion',
      );
      await _cleanupInstallerArtifacts(pendingPath);
      await _clearPendingInstallerState();
      state.value = state.value.copyWith(
        status: UpdateStatus.idle,
        clearTempApkPath: true,
      );
      return;
    }

    final verification = await _verifyApkFile(pendingPath);
    if (!verification.valid) {
      _logUpdateInstallCleanup(
        'stale_pending_path_invalid path=$pendingPath reason=${verification.reason}',
      );
      await _cleanupInstallerArtifacts(pendingPath);
      await _clearPendingInstallerState();
      state.value = state.value.copyWith(
        status: UpdateStatus.idle,
        clearTempApkPath: true,
      );
      return;
    }

    _logUpdateInstallResume(
      'ready_to_resume path=$pendingPath version=${pendingVersion ?? 'unknown'}',
    );
    state.value = state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      tempApkPath: pendingPath,
      downloadProgress: 1,
      diagnostics: state.value.diagnostics.copyWith(
        apkDownloaded: true,
        apkPath: pendingPath,
        apkFileExists: true,
      ),
    );
  }

  Future<void> _persistPendingInstallerState({
    required String apkPath,
    required String version,
  }) async {
    await _preferences.setString(_prefPendingApkPath, apkPath);
    await _preferences.setString(_prefPendingVersion, version);
    await _preferences.setInt(
      _prefPendingSavedAt,
      DateTime.now().millisecondsSinceEpoch,
    );
    _logUpdateInstallResume(
      'persisted_pending_installer path=$apkPath version=$version',
    );
  }

  Future<void> _clearPendingInstallerState() async {
    await _preferences.remove(_prefPendingApkPath);
    await _preferences.remove(_prefPendingVersion);
    await _preferences.remove(_prefPendingSavedAt);
    _logUpdateInstallCleanup('pending_state_cleared');
  }

  Future<void> _persistDownloadState({
    required String partialPath,
    required String version,
    required double progress,
    required int receivedBytes,
    int? totalBytes,
  }) async {
    await _preferences.setString(_prefDownloadPartialPath, partialPath);
    await _preferences.setString(_prefDownloadVersion, version);
    await _preferences.setDouble(_prefDownloadProgress, progress);
    await _preferences.setInt(_prefDownloadReceivedBytes, receivedBytes);
    if (totalBytes != null) {
      await _preferences.setInt(_prefDownloadTotalBytes, totalBytes);
    } else {
      await _preferences.remove(_prefDownloadTotalBytes);
    }
  }

  Future<void> _clearDownloadState() async {
    await _preferences.remove(_prefApprovedDownload);
    await _preferences.remove(_prefDownloadPartialPath);
    await _preferences.remove(_prefDownloadVersion);
    await _preferences.remove(_prefDownloadProgress);
    await _preferences.remove(_prefDownloadReceivedBytes);
    await _preferences.remove(_prefDownloadTotalBytes);
  }

  Future<Directory> _ensureVersionScopedUpdateDirectory(String version) async {
    final tempDirectory = await getTemporaryDirectory();
    final updateDirectory = Directory(
      p.join(
        tempDirectory.path,
        _updatesDirectoryName,
        _sanitizeVersionForPath(version),
      ),
    );
    if (!await updateDirectory.exists()) {
      await updateDirectory.create(recursive: true);
    }
    return updateDirectory;
  }

  Future<void> _cleanupObsoleteDownloadedApks({
    required String activeVersion,
  }) async {
    final tempDirectory = await getTemporaryDirectory();
    final updatesRoot = Directory(
      p.join(tempDirectory.path, _updatesDirectoryName),
    );
    if (!await updatesRoot.exists()) {
      return;
    }

    final activeKey = _sanitizeVersionForPath(activeVersion);
    await for (final entity in updatesRoot.list()) {
      if (entity is! Directory) {
        continue;
      }
      if (p.basename(entity.path) == activeKey) {
        continue;
      }
      try {
        await entity.delete(recursive: true);
        _logUpdateInstallCleanup('deleted_stale_directory path=${entity.path}');
      } catch (error) {
        _logUpdateInstallCleanup(
          'delete_stale_directory_failed path=${entity.path} error=$error',
        );
      }
    }

    final persistedDownloadVersion = _preferences.getString(_prefDownloadVersion);
    if (persistedDownloadVersion != null && persistedDownloadVersion != activeVersion) {
      final stalePartialPath = _preferences.getString(_prefDownloadPartialPath);
      if (stalePartialPath != null && stalePartialPath.isNotEmpty) {
        await _cleanupInstallerArtifacts(stalePartialPath);
      }
      await _clearDownloadState();
    }
  }

  Future<void> _downloadApkToPartialFile({
    required UpdateManifest manifest,
    required File partialFile,
    required int existingPartialBytes,
  }) async {
    if (Platform.isAndroid) {
      await BackgroundDownload.transfer(
        url: manifest.apkUrl,
        title: 'Aggiornamento ${manifest.version}',
        destination: partialFile,
        onProgress: (received, total) {
          state.value = state.value.copyWith(
            status: UpdateStatus.downloading,
            downloadProgress: total > 0
                ? (received / total).clamp(0.0, 1.0).toDouble() : 0.0,
          );
        },
      );
      return;
    }
    final headers = <String, dynamic>{};
    if (existingPartialBytes > 0) {
      headers[HttpHeaders.rangeHeader] = 'bytes=$existingPartialBytes-';
    }

    final response = await _dio.get<ResponseBody>(
      manifest.apkUrl,
      options: Options(
        responseType: ResponseType.stream,
        followRedirects: true,
        receiveTimeout: _downloadTimeout,
        headers: headers,
        validateStatus: (status) =>
            status != null &&
            (status == HttpStatus.ok || status == HttpStatus.partialContent),
      ),
    );

    final supportsResume =
        existingPartialBytes > 0 && response.statusCode == HttpStatus.partialContent;
    final sink = partialFile.openWrite(
      mode: supportsResume ? FileMode.append : FileMode.write,
    );
    final reportedLength =
        int.tryParse(response.headers.value(Headers.contentLengthHeader) ?? '');
    final totalBytes = supportsResume
        ? existingPartialBytes + (reportedLength ?? 0)
        : (reportedLength ?? manifest.apkSizeBytes ?? 0);

    var receivedBytes = supportsResume ? existingPartialBytes : 0;
    var lastPersistedProgress = -1.0;
    try {
      await for (final chunk in response.data!.stream) {
        sink.add(chunk);
        receivedBytes += chunk.length;
        final progress = totalBytes > 0
            ? (receivedBytes / totalBytes).clamp(0.0, 1.0)
            : 0.0;
        if (progress == 0 ||
            (progress - lastPersistedProgress).abs() >= 0.01 ||
            progress >= 1) {
          lastPersistedProgress = progress;
          _logUpdateDownloadProgress(
            'received=$receivedBytes total=${totalBytes > 0 ? totalBytes : -1} progress=${(progress * 100).toStringAsFixed(1)}%',
          );
          state.value = state.value.copyWith(
            status: UpdateStatus.downloading,
            downloadProgress: progress,
          );
          await _persistDownloadState(
            partialPath: partialFile.path,
            version: manifest.version,
            progress: progress,
            receivedBytes: receivedBytes,
            totalBytes: totalBytes > 0 ? totalBytes : manifest.apkSizeBytes,
          );
        }
      }
    } finally {
      await sink.flush();
      await sink.close();
    }
  }

  Future<_ApkVerificationResult> _verifyApkFile(
    String apkPath, {
    int? expectedSizeBytes,
  }) async {
    final apkFile = File(apkPath);
    final exists = await apkFile.exists();
    final readable = exists && await apkFile.stat().then((_) => true).catchError((_) => false);
    final sizeBytes = exists ? await apkFile.length() : 0;
    final hasApkExtension = p.extension(apkPath).toLowerCase() == '.apk';
    final minimumRequiredBytes = expectedSizeBytes != null &&
            expectedSizeBytes > _minValidApkBytes
        ? expectedSizeBytes
        : _minValidApkBytes;

    var nativeValid = true;
    var reason = 'ok';
    String? packageName;
    String? versionName;
    int? versionCode;
    String? signatureSha256;
    String? fileSha256;
    bool? hasSplitConfig;
    String? abi;
    var archiveParsed = false;
    final nativeResult = await _intentHandler.verifyApk(apkPath);
    nativeResult.fold(
      (failure) {
        if (!failure.message.toLowerCase().contains('not available on this platform')) {
          nativeValid = false;
          reason = failure.message;
        }
      },
      (payload) {
        nativeValid = payload['valid'] == true;
        reason = (payload['reason'] as String?) ?? (nativeValid ? 'ok' : 'unknown');
        packageName = payload['packageName'] as String?;
        versionName = payload['versionName'] as String?;
        versionCode = _parseInt(payload['versionCode']);
        signatureSha256 = payload['signatureSha256'] as String?;
        fileSha256 = payload['fileSha256'] as String?;
        hasSplitConfig = payload['hasSplitConfig'] as bool?;
        abi = payload['abi'] as String?;
        archiveParsed = payload['archiveParsed'] == true;
      },
    );

    if (!exists) {
      reason = 'missing';
    } else if (!readable) {
      reason = 'not_readable';
    } else if (!hasApkExtension) {
      reason = 'invalid_extension';
    } else if (sizeBytes < minimumRequiredBytes) {
      reason = 'below_minimum_size';
    } else if (!nativeValid) {
      reason = reason == 'ok' ? 'package_parse_failed' : reason;
    }

    final valid = exists &&
        readable &&
        hasApkExtension &&
        sizeBytes >= minimumRequiredBytes &&
        nativeValid;
    _logUpdateApkVerify(
      'path=$apkPath valid=$valid exists=$exists readable=$readable size_bytes=$sizeBytes reason=$reason',
    );
    return _ApkVerificationResult(
      valid: valid,
      exists: exists,
      readable: readable,
      hasApkExtension: hasApkExtension,
      sizeBytes: sizeBytes,
      reason: reason,
      packageName: packageName,
      versionName: versionName,
      versionCode: versionCode,
      signatureSha256: signatureSha256,
      fileSha256: fileSha256,
      hasSplitConfig: hasSplitConfig,
      abi: abi,
      archiveParsed: archiveParsed,
    );
  }

  Future<_InstalledIdentity> _readInstalledIdentity({
    bool includeDiagnostics = true,
  }) async {
    final packageInfo = await PackageInfo.fromPlatform();
    String? installerPackage;
    String? signatureSha256;
    int? installedVersionCode;
    if (includeDiagnostics) {
      final diagnosticsResult = await _intentHandler.getInstallDiagnostics();
      diagnosticsResult.fold(
        (_) {},
        (map) {
          installerPackage = map['installerPackageName'] as String?;
          signatureSha256 = map['installedSignatureSha256'] as String?;
          installedVersionCode = _parseInt(map['installedVersionCode']);
        },
      );
    }
    return _InstalledIdentity(
      versionName: packageInfo.version,
      versionCode: installedVersionCode ?? _parseInt(packageInfo.buildNumber),
      applicationId: packageInfo.packageName,
      installerPackage: installerPackage,
      signatureSha256: signatureSha256,
    );
  }

  Future<void> _runPostInstallVerification({
    required int? beforeInstallVersionCode,
    required int? expectedVersionCode,
    required String? expectedVersionName,
    required String? releaseTag,
  }) async {
    _logUpdatePostVerify(
      'phase=begin '
      'installed_before_version_code=${beforeInstallVersionCode?.toString() ?? '-'} '
      'expected_version_code=${expectedVersionCode?.toString() ?? '-'} '
      'expected_version_name=${expectedVersionName ?? '-'} '
      'release_tag=${releaseTag ?? '-'}',
    );
    _InstalledIdentity? post;
    for (var attempt = 1; attempt <= _postInstallVerifyMaxAttempts; attempt++) {
      post = await _readInstalledIdentity();
      final changed = beforeInstallVersionCode != null &&
          post.versionCode != null &&
          post.versionCode != beforeInstallVersionCode;
      if (changed) {
        _logUpdatePostVerifyOk(
          'attempt=$attempt '
          'installed_after_version_code=${post.versionCode} '
          'installed_after_version_name=${post.versionName} '
          'application_id=${post.applicationId}',
        );
        return;
      }
      if (attempt < _postInstallVerifyMaxAttempts) {
        await Future<void>.delayed(_postInstallVerifyPollInterval);
      }
    }
    final installedVersionCode = post?.versionCode;
    final installedVersionName = post?.versionName;
    final installedApplicationId = post?.applicationId;
    _logUpdatePostVerifyFailed(
      'installed_before_version_code=${beforeInstallVersionCode?.toString() ?? '-'} '
      'installed_after_version_code=${installedVersionCode?.toString() ?? '-'} '
      'installed_after_version_name=${installedVersionName ?? '-'} '
      'expected_version_code=${expectedVersionCode?.toString() ?? '-'} '
      'expected_version_name=${expectedVersionName ?? '-'} '
      'application_id=${installedApplicationId ?? '-'}',
    );
    _logStructuredUpdateError(
      action: 'post_install_verify',
      detectedVersion: releaseTag,
      selectedChannel: state.value.preferredChannel,
      comparisonResult: _comparisonResultFor(releaseTag),
      finalDecisionState: state.value.status.name,
      message: 'Post-install verification failed: installed version unchanged',
    );
  }

  Future<void> _logReleaseForensicsCheck(UpdateManifest manifest) async {
    _InstalledIdentity? installedIdentity;
    try {
      installedIdentity = await _readInstalledIdentity(includeDiagnostics: false);
    } catch (_) {}
    final localVersionName = installedIdentity?.versionName ?? _currentVersion;
    final localVersionCode = installedIdentity?.versionCode ??
        _parseBuildNumberFromVersion(_currentVersion);
    _logUpdateCheck(
      'application_id=${installedIdentity?.applicationId ?? '-'} '
      'installed_version_name=$localVersionName '
      'installed_version_code=${localVersionCode?.toString() ?? '-'} '
      'target_version_name=${manifest.version} '
      'target_version_code=${manifest.versionCode?.toString() ?? '-'} '
      'apk_filename=${manifest.apkFileName ?? '-'} '
      'apk_size_bytes=${manifest.apkSizeBytes ?? -1} '
      'release_tag=${manifest.version} '
      'sha256=${installedIdentity?.signatureSha256 ?? '-'} '
      'installer_package=${installedIdentity?.installerPackage ?? '-'}',
    );
  }

  int? _parseBuildNumberFromVersion(String version) {
    final buildSeparatorIndex = version.lastIndexOf('+');
    if (buildSeparatorIndex < 0) {
      return null;
    }
    return int.tryParse(version.substring(buildSeparatorIndex + 1));
  }

  int? _parseInt(Object? value) {
    return switch (value) {
      int v => v,
      String v => int.tryParse(v.trim()),
      _ => null,
    };
  }

  String _resolveApkFileName(UpdateManifest manifest, Uri uri) {
    final manifestName = manifest.apkFileName?.trim();
    if (manifestName != null &&
        manifestName.isNotEmpty &&
        !manifestName.contains('/') &&
        manifestName.toLowerCase().endsWith('.apk')) {
      return manifestName;
    }

    if (uri.pathSegments.isNotEmpty) {
      final uriName = uri.pathSegments.last.trim();
      if (uriName.isNotEmpty &&
          !uriName.contains('/') &&
          uriName.toLowerCase().endsWith('.apk')) {
        return uriName;
      }
    }

    return _defaultApkFileName;
  }

  String _sanitizeVersionForPath(String version) {
    return version.toLowerCase().replaceAll(RegExp(r'[^a-z0-9._-]+'), '_');
  }

  Future<void> _cleanupInstallerArtifacts(String apkPath) async {
    final file = File(apkPath);
    if (!await file.exists()) {
      _logUpdateInstallCleanup('apk_missing path=$apkPath');
      return;
    }
    try {
      await file.delete();
      _logUpdateInstallCleanup('apk_deleted path=$apkPath');
    } catch (error) {
      _logUpdateInstallCleanup('apk_delete_failed path=$apkPath error=$error');
    }
  }

  void _logUpdate(String message) => debugPrint('[UPDATE] $message');
  void _logApk(String message) => debugPrint('[APK] $message');
  void _logInstall(String message) => debugPrint('[INSTALL] $message');
  void _logUpdateCheck(String message) => debugPrint('[UPDATE_CHECK] $message');
  void _logUpdateDownload(String message) => debugPrint('[UPDATE_DOWNLOAD] $message');
  void _logUpdateApkReady(String message) => debugPrint('[UPDATE_APK_READY] $message');
  void _logUpdateInstallBegin(String message) =>
      debugPrint('[UPDATE_INSTALL_BEGIN] $message');
  void _logUpdateInstallResult(String message) =>
      debugPrint('[UPDATE_INSTALL_RESULT] $message');
  void _logUpdatePostVerify(String message) =>
      debugPrint('[UPDATE_POST_VERIFY] $message');
  void _logVersionRejected(String message) =>
      debugPrint('[UPDATE_VERSION_REJECTED] $message');
  void _logSignatureCurrent(String message) =>
      debugPrint('[UPDATE_SIGNATURE_CURRENT] $message');
  void _logSignatureNew(String message) =>
      debugPrint('[UPDATE_SIGNATURE_NEW] $message');
  void _logSignatureMismatch(String message) =>
      debugPrint('[UPDATE_SIGNATURE_MISMATCH] $message');
  void _logUpdatePostVerifyFailed(String message) =>
      debugPrint('[UPDATE_POST_VERIFY_FAILED] $message');
  void _logUpdatePostVerifyOk(String message) =>
      debugPrint('[UPDATE_POST_VERIFY_OK] $message');
  void _logUpdateApkAnalysis(String message) =>
      debugPrint('[UPDATE_APK_ANALYSIS] $message');
  void _logVersionLocal(String message) =>
      debugPrint('[UPDATE_VERSION_LOCAL] $message');
  void _logVersionRemote(String message) =>
      debugPrint('[UPDATE_VERSION_REMOTE] $message');
  void _logVersionCompare(String message) =>
      debugPrint('[UPDATE_VERSION_COMPARE] $message');
  void _logUpdateDownloadStart(String message) =>
      debugPrint('[UPDATE_DOWNLOAD_START] $message');
  void _logUpdateDownloadProgress(String message) =>
      debugPrint('[UPDATE_DOWNLOAD_PROGRESS] $message');
  void _logUpdateDownloadComplete(String message) =>
      debugPrint('[UPDATE_DOWNLOAD_COMPLETE] $message');
  void _logUpdateDownloadFail(String message) =>
      debugPrint('[UPDATE_DOWNLOAD_FAIL] $message');
  void _logUpdateApkVerify(String message) =>
      debugPrint('[UPDATE_APK_VERIFY] $message');
  void _logUpdateInstallStart() => debugPrint('[UPDATE_INSTALL_START] begin');
  void _logUpdateInstallFail(String reason) =>
      debugPrint('[UPDATE_INSTALL_FAIL] reason=$reason');
  void _logUpdateInstallResume(String message) =>
      debugPrint('[UPDATE_INSTALL_RESUME] $message');
  void _logUpdateInstallSuccess() =>
      debugPrint('[UPDATE_INSTALL_SUCCESS] launched=true');
  void _logUpdateInstallCleanup(String message) =>
      debugPrint('[UPDATE_INSTALL_CLEANUP] $message');
  void _logStructuredUpdateCheck({
    required ReleaseChannel selectedChannel,
    required String finalDecisionState,
    String? detectedVersion,
    int? comparisonResult,
  }) {
    _logUpdate(
      'check current_version=$_currentVersion '
      'detected_version=${detectedVersion ?? '-'} '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=${comparisonResult ?? 'n/a'} '
      'final_decision_state=$finalDecisionState',
    );
    debugPrint(
      '[UPDATE_CHECK] current_version=$_currentVersion '
      'detected_version=${detectedVersion ?? '-'} '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=${comparisonResult ?? 'n/a'} '
      'final_decision_state=$finalDecisionState',
    );
  }

  void _logStructuredVersionCompare({
    required String detectedVersion,
    required ReleaseChannel selectedChannel,
    required int comparisonResult,
    required bool compatible,
    required String finalDecisionState,
  }) {
    _logVersionCompare(
      'current_version=$_currentVersion '
      'detected_version=$detectedVersion '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=$comparisonResult '
      'compatible=$compatible '
      'final_decision_state=$finalDecisionState',
    );
    debugPrint(
      '[VERSION_COMPARE] current_version=$_currentVersion '
      'detected_version=$detectedVersion '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=$comparisonResult '
      'compatible=$compatible '
      'final_decision_state=$finalDecisionState',
    );
  }

  void _logStructuredUpdateAvailable({
    required String detectedVersion,
    required ReleaseChannel selectedChannel,
    required int comparisonResult,
    required String finalDecisionState,
  }) {
    debugPrint(
      '[UPDATE_AVAILABLE] current_version=$_currentVersion '
      'detected_version=$detectedVersion '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=$comparisonResult '
      'final_decision_state=$finalDecisionState',
    );
  }

  void _logStructuredDownloadTrigger({
    required ReleaseChannel selectedChannel,
    required String finalDecisionState,
    String? detectedVersion,
    int? comparisonResult,
  }) {
    debugPrint(
      '[DOWNLOAD_TRIGGER] current_version=$_currentVersion '
      'detected_version=${detectedVersion ?? '-'} '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=${comparisonResult ?? 'n/a'} '
      'final_decision_state=$finalDecisionState',
    );
  }

  void _logStructuredInstallTrigger({
    required ReleaseChannel selectedChannel,
    required String finalDecisionState,
    String? detectedVersion,
    int? comparisonResult,
  }) {
    debugPrint(
      '[INSTALL_TRIGGER] current_version=$_currentVersion '
      'detected_version=${detectedVersion ?? '-'} '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=${comparisonResult ?? 'n/a'} '
      'final_decision_state=$finalDecisionState',
    );
  }

  void _logStructuredUpdateError({
    required String action,
    required ReleaseChannel selectedChannel,
    required String finalDecisionState,
    required String message,
    String? detectedVersion,
    int? comparisonResult,
  }) {
    debugPrint(
      '[UPDATE_ERROR] action=$action current_version=$_currentVersion '
      'detected_version=${detectedVersion ?? '-'} '
      'selected_channel=${selectedChannel.storageValue} '
      'comparison_result=${comparisonResult ?? 'n/a'} '
      'final_decision_state=$finalDecisionState '
      'message=$message',
    );
  }

  void dispose() {
    stopBackgroundChecks();
    state.dispose();
  }
}

