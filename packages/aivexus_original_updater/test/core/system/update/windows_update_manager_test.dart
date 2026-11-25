import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/windows_update_installer.dart';
import 'package:aivexus_original_updater/core/system/update/windows_update_manager.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

class MockUpdateChecker extends Mock implements UpdateChecker {}

class MockAndroidIntentHandler extends Mock implements AndroidIntentHandler {}

class FakeWindowsUpdateInstaller implements WindowsUpdateInstallerPort {
  int downloadCalls = 0;
  int verifyCalls = 0;
  int launchCalls = 0;
  String? lastUrl;
  String? lastFileName;
  String? lastFinalPath;
  int? lastExpectedSize;
  String? lastExpectedSha;

  WindowsInstallerVerification verification =
      const WindowsInstallerVerification(
    valid: true,
    exists: true,
    sizeBytes: 4096,
    sha256:
        'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd',
    reason: 'ok',
  );
  bool launchResult = true;

  @override
  Future<String> download({
    required String url,
    required String fileName,
    required String finalPath,
    required String partialPath,
    required int expectedSizeBytes,
    required String expectedSha256,
    required void Function(int received, int total) onProgress,
  }) async {
    downloadCalls++;
    lastUrl = url;
    lastFileName = fileName;
    lastFinalPath = finalPath;
    lastExpectedSize = expectedSizeBytes;
    lastExpectedSha = expectedSha256;
    final file = File(finalPath);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(const <int>[0x4d, 0x5a, 0x90, 0x00], flush: true);
    onProgress(expectedSizeBytes, expectedSizeBytes);
    return finalPath;
  }

  @override
  Future<WindowsInstallerVerification> verify({
    required String filePath,
    required int expectedSizeBytes,
    required String expectedSha256,
  }) async {
    verifyCalls++;
    return verification;
  }

  @override
  Future<bool> launch(String filePath) async {
    launchCalls++;
    return launchResult;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDirectory;
  late SharedPreferences preferences;
  late MockUpdateChecker updateChecker;
  late MockAndroidIntentHandler intentHandler;
  late FakeWindowsUpdateInstaller installer;
  late WindowsUpdateManager manager;

  const sha =
      'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd';

  UpdateManifest verifiedManifest({String version = '1.0.14.300'}) {
    return UpdateManifest.fromJson(<String, dynamic>{
      'versionName': version,
      'versionCode': 300,
      'apkUrl': 'https://example.com/app-release.apk',
      'windowsUrl': 'https://example.com/AI-Orchestrator-Setup-x64.exe',
      'windowsFileName': 'AI-Orchestrator-Setup-x64.exe',
      'windowsSizeBytes': 4096,
      'windowsSha256': sha,
    });
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    preferences = await SharedPreferences.getInstance();
    tempDirectory = await Directory.systemTemp.createTemp(
      'ai-orchestrator-windows-update-manager-',
    );
    updateChecker = MockUpdateChecker();
    intentHandler = MockAndroidIntentHandler();
    installer = FakeWindowsUpdateInstaller();
    manager = WindowsUpdateManager(
      updateChecker: updateChecker,
      comparator: const VersionComparator(),
      preferences: preferences,
      intentHandler: intentHandler,
      currentVersion: '1.0.13.299',
      windowsInstaller: installer,
      temporaryDirectoryProvider: () async => tempDirectory,
    );
  });

  tearDown(() async {
    manager.stopBackgroundChecks();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('refuses download when verified Windows artifact metadata is missing',
      () async {
    final manifest = UpdateManifest.fromJson(const <String, dynamic>{
      'versionName': '1.0.14.300',
      'versionCode': 300,
      'apkUrl': 'https://example.com/app-release.apk',
    });
    manager.state.value = manager.state.value.copyWith(
      status: UpdateStatus.updateAvailable,
      latestManifest: manifest,
    );

    final result = await manager.downloadLatestApk();

    expect(result, isFalse);
    expect(installer.downloadCalls, 0);
    expect(manager.state.value.status, UpdateStatus.error);
    expect(manager.state.value.errorMessage,
        contains('verified Windows installer'));
  });

  test('downloads exact verified EXE metadata and persists pending installer',
      () async {
    final manifest = verifiedManifest();
    manager.state.value = manager.state.value.copyWith(
      status: UpdateStatus.updateAvailable,
      latestManifest: manifest,
    );

    final result = await manager.downloadLatestApk();

    expect(result, isTrue);
    expect(installer.downloadCalls, 1);
    expect(installer.lastUrl,
        'https://example.com/AI-Orchestrator-Setup-x64.exe');
    expect(installer.lastFileName, 'AI-Orchestrator-Setup-x64.exe');
    expect(installer.lastExpectedSize, 4096);
    expect(installer.lastExpectedSha, sha);
    expect(manager.state.value.status, UpdateStatus.readyToInstall);
    expect(manager.state.value.downloadProgress, 1);
    expect(await File(installer.lastFinalPath!).exists(), isTrue);
    expect(
      preferences.getString('update_windows_pending_path'),
      installer.lastFinalPath,
    );
    expect(
      preferences.getString('update_windows_pending_version'),
      manifest.version,
    );
    expect(preferences.getInt('update_windows_pending_size'), 4096);
    expect(preferences.getString('update_windows_pending_sha256'), sha);
  });

  test('re-verifies before launch and clears an invalid pending EXE',
      () async {
    final manifest = verifiedManifest();
    manager.state.value = manager.state.value.copyWith(
      status: UpdateStatus.updateAvailable,
      latestManifest: manifest,
    );
    expect(await manager.downloadLatestApk(), isTrue);
    final downloadedPath = installer.lastFinalPath!;
    installer.verification = const WindowsInstallerVerification(
      valid: false,
      exists: true,
      sizeBytes: 4096,
      sha256: '00',
      reason: 'installer SHA-256 mismatch',
    );

    final result = await manager.prepareInstallIntent();

    expect(result, isFalse);
    expect(installer.verifyCalls, 1);
    expect(installer.launchCalls, 0);
    expect(await File(downloadedPath).exists(), isFalse);
    expect(preferences.getString('update_windows_pending_path'), isNull);
    expect(manager.state.value.status, UpdateStatus.error);
    expect(manager.state.value.errorMessage, contains('failed verification'));
  });

  test('launches only after successful re-verification and records diagnostics',
      () async {
    final manifest = verifiedManifest();
    manager.state.value = manager.state.value.copyWith(
      status: UpdateStatus.updateAvailable,
      latestManifest: manifest,
    );
    expect(await manager.downloadLatestApk(), isTrue);

    final result = await manager.prepareInstallIntent();

    expect(result, isTrue);
    expect(installer.verifyCalls, 1);
    expect(installer.launchCalls, 1);
    expect(manager.state.value.status, UpdateStatus.readyToInstall);
    expect(manager.state.value.diagnostics.installerLaunchSuccess, isTrue);
    expect(manager.state.value.diagnostics.apkFileExists, isTrue);
  });

  test('restores a persisted verified EXE after manager recreation', () async {
    final manifest = verifiedManifest();
    manager.state.value = manager.state.value.copyWith(
      status: UpdateStatus.updateAvailable,
      latestManifest: manifest,
    );
    expect(await manager.downloadLatestApk(), isTrue);
    final pendingPath = installer.lastFinalPath!;

    final restoredInstaller = FakeWindowsUpdateInstaller();
    final restored = WindowsUpdateManager(
      updateChecker: updateChecker,
      comparator: const VersionComparator(),
      preferences: preferences,
      intentHandler: intentHandler,
      currentVersion: '1.0.13.299',
      windowsInstaller: restoredInstaller,
      temporaryDirectoryProvider: () async => tempDirectory,
    );

    await restored.refreshDiagnostics();

    expect(restoredInstaller.verifyCalls, 1);
    expect(restored.state.value.status, UpdateStatus.readyToInstall);
    expect(restored.state.value.tempApkPath, pendingPath);
    expect(restored.state.value.latestManifest?.version, manifest.version);
    restored.stopBackgroundChecks();
  });
}
