import 'dart:io';

import 'package:get_it/get_it.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aivexus_original_updater/core/system/update/linux_update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/macos_update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_checker.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_manifest.dart';
import 'package:aivexus_original_updater/core/system/update/version_comparator.dart';
import 'package:aivexus_original_updater/core/system/update/windows_update_manager.dart';
import 'package:aivexus_original_updater/native/platform/android_intent_handler.dart';

Future<void> configurePlatformUpdateServices(
  GetIt sl, {
  required String currentVersion,
  required String manifestUrl,
  required String githubOwner,
  required String githubRepo,
  required String windowsSetupAssetName,
  required String macosDmgAssetName,
  required String linuxDebAssetName,
}) async {
  if (!Platform.isWindows && !Platform.isMacOS && !Platform.isLinux) return;

  if (sl.isRegistered<UpdateManager>()) {
    await sl.unregister<UpdateManager>();
  }
  if (sl.isRegistered<UpdateChecker>()) {
    await sl.unregister<UpdateChecker>();
  }

  final targetPlatform = Platform.isWindows
      ? UpdateTargetPlatform.windows
      : Platform.isMacOS
          ? UpdateTargetPlatform.macos
          : UpdateTargetPlatform.linux;

  sl.registerLazySingleton<UpdateChecker>(
    () => UpdateChecker(
      httpClient: sl<http.Client>(),
      preferences: sl<SharedPreferences>(),
      comparator: sl<VersionComparator>(),
      manifestUrl: manifestUrl,
      githubOwner: githubOwner,
      githubRepo: githubRepo,
      targetPlatform: targetPlatform,
      windowsSetupAssetName: windowsSetupAssetName,
      macosDmgAssetName: macosDmgAssetName,
      linuxDebAssetName: linuxDebAssetName,
    ),
  );

  if (Platform.isWindows) {
    sl.registerLazySingleton<UpdateManager>(
      () => WindowsUpdateManager(
        updateChecker: sl<UpdateChecker>(),
        comparator: sl<VersionComparator>(),
        preferences: sl<SharedPreferences>(),
        intentHandler: sl<AndroidIntentHandler>(),
        currentVersion: currentVersion,
      ),
    );
    return;
  }

  if (Platform.isMacOS) {
    sl.registerLazySingleton<UpdateManager>(
      () => MacosUpdateManager(
        updateChecker: sl<UpdateChecker>(),
        comparator: sl<VersionComparator>(),
        preferences: sl<SharedPreferences>(),
        intentHandler: sl<AndroidIntentHandler>(),
        currentVersion: currentVersion,
      ),
    );
    return;
  }

  sl.registerLazySingleton<UpdateManager>(
    () => LinuxUpdateManager(
      updateChecker: sl<UpdateChecker>(),
      comparator: sl<VersionComparator>(),
      preferences: sl<SharedPreferences>(),
      intentHandler: sl<AndroidIntentHandler>(),
      currentVersion: currentVersion,
    ),
  );
}
