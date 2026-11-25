import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';

enum UpdateStatus {
  idle,
  checking,
  upToDate,
  updateAvailable,
  downloading,
  readyToInstall,
  error,
}

class UpdateDiagnostics {
  const UpdateDiagnostics({
    this.remoteVersion,
    this.remoteVersionCode,
    this.updateUrl,
    this.apkDownloaded = false,
    this.apkPath,
    this.apkFileExists = false,
    this.installerLaunchSuccess,
    this.lastException,
    this.androidSdkInt,
    this.canRequestPackageInstalls,
    this.lastInstallerResultCode,
  });

  final String? remoteVersion;
  final int? remoteVersionCode;
  final String? updateUrl;
  final bool apkDownloaded;
  final String? apkPath;
  final bool apkFileExists;
  final bool? installerLaunchSuccess;
  final String? lastException;
  final int? androidSdkInt;
  final bool? canRequestPackageInstalls;
  final int? lastInstallerResultCode;

  UpdateDiagnostics copyWith({
    String? remoteVersion,
    bool clearRemoteVersion = false,
    int? remoteVersionCode,
    bool clearRemoteVersionCode = false,
    String? updateUrl,
    bool clearUpdateUrl = false,
    bool? apkDownloaded,
    String? apkPath,
    bool clearApkPath = false,
    bool? apkFileExists,
    bool? installerLaunchSuccess,
    bool clearInstallerLaunchSuccess = false,
    String? lastException,
    bool clearLastException = false,
    int? androidSdkInt,
    bool clearAndroidSdkInt = false,
    bool? canRequestPackageInstalls,
    bool clearCanRequestPackageInstalls = false,
    int? lastInstallerResultCode,
    bool clearLastInstallerResultCode = false,
  }) {
    return UpdateDiagnostics(
      remoteVersion:
          clearRemoteVersion ? null : (remoteVersion ?? this.remoteVersion),
      remoteVersionCode: clearRemoteVersionCode
          ? null
          : (remoteVersionCode ?? this.remoteVersionCode),
      updateUrl: clearUpdateUrl ? null : (updateUrl ?? this.updateUrl),
      apkDownloaded: apkDownloaded ?? this.apkDownloaded,
      apkPath: clearApkPath ? null : (apkPath ?? this.apkPath),
      apkFileExists: apkFileExists ?? this.apkFileExists,
      installerLaunchSuccess: clearInstallerLaunchSuccess
          ? null
          : (installerLaunchSuccess ?? this.installerLaunchSuccess),
      lastException:
          clearLastException ? null : (lastException ?? this.lastException),
      androidSdkInt:
          clearAndroidSdkInt ? null : (androidSdkInt ?? this.androidSdkInt),
      canRequestPackageInstalls: clearCanRequestPackageInstalls
          ? null
          : (canRequestPackageInstalls ?? this.canRequestPackageInstalls),
      lastInstallerResultCode: clearLastInstallerResultCode
          ? null
          : (lastInstallerResultCode ?? this.lastInstallerResultCode),
    );
  }
}

class UpdateState {
  const UpdateState({
    required this.status,
    required this.currentVersion,
    required this.preferredChannel,
    this.latestManifest,
    this.downloadProgress = 0,
    this.tempApkPath,
    this.errorMessage,
    this.lastCheckedAt,
    this.usedCachedManifest = false,
    this.diagnostics = const UpdateDiagnostics(),
  });

  final UpdateStatus status;
  final String currentVersion;
  final ReleaseChannel preferredChannel;
  final UpdateManifest? latestManifest;
  final double downloadProgress;
  final String? tempApkPath;
  final String? errorMessage;
  final DateTime? lastCheckedAt;
  final bool usedCachedManifest;
  final UpdateDiagnostics diagnostics;

  bool get hasUpdate => status == UpdateStatus.updateAvailable && latestManifest != null;

  UpdateState copyWith({
    UpdateStatus? status,
    String? currentVersion,
    ReleaseChannel? preferredChannel,
    UpdateManifest? latestManifest,
    bool clearLatestManifest = false,
    double? downloadProgress,
    String? tempApkPath,
    bool clearTempApkPath = false,
    String? errorMessage,
    bool clearErrorMessage = false,
    DateTime? lastCheckedAt,
    bool? usedCachedManifest,
    UpdateDiagnostics? diagnostics,
  }) {
    return UpdateState(
      status: status ?? this.status,
      currentVersion: currentVersion ?? this.currentVersion,
      preferredChannel: preferredChannel ?? this.preferredChannel,
      latestManifest:
          clearLatestManifest ? null : (latestManifest ?? this.latestManifest),
      downloadProgress: downloadProgress ?? this.downloadProgress,
      tempApkPath: clearTempApkPath ? null : (tempApkPath ?? this.tempApkPath),
      errorMessage:
          clearErrorMessage ? null : (errorMessage ?? this.errorMessage),
      lastCheckedAt: lastCheckedAt ?? this.lastCheckedAt,
      usedCachedManifest: usedCachedManifest ?? this.usedCachedManifest,
      diagnostics: diagnostics ?? this.diagnostics,
    );
  }

  static UpdateState initial({
    required String currentVersion,
    required ReleaseChannel preferredChannel,
  }) {
    return UpdateState(
      status: UpdateStatus.idle,
      currentVersion: currentVersion,
      preferredChannel: preferredChannel,
    );
  }
}
