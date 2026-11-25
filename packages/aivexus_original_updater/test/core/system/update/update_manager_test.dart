import 'dart:io';

import 'package:dartz/dartz.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

class MockUpdateChecker extends Mock implements UpdateChecker {}

class MockAndroidIntentHandler extends Mock implements AndroidIntentHandler {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late MockUpdateChecker mockUpdateChecker;
  late MockAndroidIntentHandler mockIntentHandler;
  late SharedPreferences preferences;
  late UpdateManager updateManager;
  const packageInfoChannel =
      MethodChannel('dev.fluttercommunity.plus/package_info');

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    preferences = await SharedPreferences.getInstance();
    mockUpdateChecker = MockUpdateChecker();
    mockIntentHandler = MockAndroidIntentHandler();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(packageInfoChannel, (call) async {
      return <String, dynamic>{
        'appName': 'AI Orchestrator',
        'packageName': 'com.aiorchestrator',
        'version': '1.12.119',
        'buildNumber': '119',
        'buildSignature': 'test',
      };
    });
    updateManager = UpdateManager(
      updateChecker: mockUpdateChecker,
      comparator: const VersionComparator(),
      preferences: preferences,
      intentHandler: mockIntentHandler,
      currentVersion: '1.12.119+119',
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(packageInfoChannel, null);
  });

  test('marks a newer simplified manifest as updateAvailable', () async {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.12.120',
      'apkUrl': 'https://example.com/app-release.apk',
      'forceUpdate': false,
    });
    when(
      () => mockUpdateChecker.checkLatestManifest(
        preferredChannel: ReleaseChannel.stable,
        allowCachedFallback: true,
      ),
    ).thenAnswer(
      (_) async => UpdateCheckResult(
        manifest: manifest,
        usedCache: false,
      ),
    );

    await updateManager.checkForUpdates();

    expect(updateManager.state.value.status, UpdateStatus.updateAvailable);
    expect(updateManager.state.value.latestManifest?.version, 'v1.12.120');
    expect(updateManager.hasDetectedNewerVersion(updateManager.state.value), isTrue);
  });

  test('blocks update via min_supported even when a newer version is detected', () async {
    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.12.120',
      'min_supported': '1.12.120',
      'apkUrl': 'https://example.com/app-release.apk',
      'forceUpdate': false,
    });
    when(
      () => mockUpdateChecker.checkLatestManifest(
        preferredChannel: ReleaseChannel.stable,
        allowCachedFallback: true,
      ),
    ).thenAnswer(
      (_) async => UpdateCheckResult(
        manifest: manifest,
        usedCache: false,
      ),
    );

    await updateManager.checkForUpdates();

    expect(updateManager.state.value.status, UpdateStatus.upToDate);
    expect(updateManager.hasDetectedNewerVersion(updateManager.state.value), isTrue);
    expect(updateManager.state.value.preferredChannel, ReleaseChannel.stable);
  });

  test('rejects install when APK versionCode is not newer than installed', () async {
    final tempDir = await Directory.systemTemp.createTemp('update-manager-test-');
    final apkFile = File('${tempDir.path}/candidate.apk');
    await apkFile.writeAsBytes(Uint8List(80 * 1024));

    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.12.120',
      'versionCode': 120,
      'apkUrl': 'https://example.com/app-release.apk',
      'forceUpdate': false,
    });
    updateManager.state.value = updateManager.state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      latestManifest: manifest,
      tempApkPath: apkFile.path,
    );

    when(
      () => mockIntentHandler.getInstallDiagnostics(),
    ).thenAnswer(
      (_) async => const Right(<String, dynamic>{
        'installerPackageName': 'com.android.packageinstaller',
        'installedSignatureSha256': 'AA:BB',
      }),
    );
    when(
      () => mockIntentHandler.verifyApk(any()),
    ).thenAnswer(
      (_) async => const Right(<String, dynamic>{
        'valid': true,
        'reason': 'ok',
        'packageName': 'com.aiorchestrator',
        'versionName': '1.12.119',
        'versionCode': 119,
        'signatureSha256': 'AA:BB',
        'fileSha256': '1234',
        'hasSplitConfig': false,
        'abi': 'arm64-v8a',
        'archiveParsed': true,
      }),
    );

    final result = await updateManager.prepareInstallIntent();

    expect(result, isFalse);
    expect(updateManager.state.value.status, UpdateStatus.error);
    expect(updateManager.state.value.errorMessage, contains('versionCode'));
    verifyNever(() => mockIntentHandler.openApkInstaller(any()));
    await tempDir.delete(recursive: true);
  });

  test('rejects install when APK signature differs from installed app', () async {
    final strictUpdateManager = UpdateManager(
      updateChecker: mockUpdateChecker,
      comparator: const VersionComparator(),
      preferences: preferences,
      intentHandler: mockIntentHandler,
      currentVersion: '1.12.119+119',
      allowDebugSignatureMismatchBypass: false,
    );
    final tempDir = await Directory.systemTemp.createTemp('update-manager-test-');
    final apkFile = File('${tempDir.path}/candidate.apk');
    await apkFile.writeAsBytes(Uint8List(80 * 1024));

    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.12.120',
      'versionCode': 120,
      'apkUrl': 'https://example.com/app-release.apk',
      'forceUpdate': false,
    });
    strictUpdateManager.state.value = strictUpdateManager.state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      latestManifest: manifest,
      tempApkPath: apkFile.path,
    );

    when(
      () => mockIntentHandler.getInstallDiagnostics(),
    ).thenAnswer(
      (_) async => const Right(<String, dynamic>{
        'installerPackageName': 'com.android.packageinstaller',
        'installedSignatureSha256': 'AA:BB',
      }),
    );
    when(
      () => mockIntentHandler.verifyApk(any()),
    ).thenAnswer(
      (_) async => const Right(<String, dynamic>{
        'valid': true,
        'reason': 'ok',
        'packageName': 'com.aiorchestrator',
        'versionName': '1.12.120',
        'versionCode': 120,
        'signatureSha256': 'CC:DD',
        'fileSha256': '1234',
        'hasSplitConfig': false,
        'abi': 'arm64-v8a',
        'archiveParsed': true,
      }),
    );

    final result = await strictUpdateManager.prepareInstallIntent();

    expect(result, isFalse);
    expect(strictUpdateManager.state.value.status, UpdateStatus.error);
    expect(strictUpdateManager.state.value.errorMessage, contains('signature'));
    verifyNever(() => mockIntentHandler.openApkInstaller(any()));
    await tempDir.delete(recursive: true);
  });

  test('bypasses signature mismatch when debug bypass is enabled and launches installer', () async {
    final tempDir = await Directory.systemTemp.createTemp('update-manager-test-');
    final apkFile = File('${tempDir.path}/candidate.apk');
    await apkFile.writeAsBytes(Uint8List(80 * 1024));

    final manifest = UpdateManifest.fromJson(const {
      'versionName': '1.12.120',
      'versionCode': 120,
      'apkUrl': 'https://example.com/app-release.apk',
      'forceUpdate': false,
    });
    updateManager.state.value = updateManager.state.value.copyWith(
      status: UpdateStatus.readyToInstall,
      latestManifest: manifest,
      tempApkPath: apkFile.path,
    );

    when(
      () => mockIntentHandler.getInstallDiagnostics(),
    ).thenAnswer(
      (_) async => const Right(<String, dynamic>{
        'installerPackageName': 'com.android.packageinstaller',
        'installedSignatureSha256': 'AA:BB',
        'installedVersionCode': 119,
      }),
    );
    when(
      () => mockIntentHandler.verifyApk(any()),
    ).thenAnswer(
      (_) async => const Right(<String, dynamic>{
        'valid': true,
        'reason': 'ok',
        'packageName': 'com.aiorchestrator',
        'versionName': '1.12.120',
        'versionCode': 120,
        'signatureSha256': 'CC:DD',
        'fileSha256': '1234',
        'hasSplitConfig': false,
        'abi': 'arm64-v8a',
        'archiveParsed': true,
      }),
    );
    when(
      () => mockIntentHandler.openApkInstaller(any()),
    ).thenAnswer((_) async => const Right(true));

    final result = await updateManager.prepareInstallIntent();

    expect(result, isTrue);
    expect(updateManager.state.value.status, isNot(UpdateStatus.error));
    verify(() => mockIntentHandler.openApkInstaller(apkFile.path)).called(1);
    await tempDir.delete(recursive: true);
  });
}
