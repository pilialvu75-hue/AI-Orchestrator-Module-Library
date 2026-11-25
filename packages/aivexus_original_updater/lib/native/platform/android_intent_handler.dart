import 'package:dartz/dartz.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:aivexus_original_updater/core/config/app/app_constants.dart';
import 'package:aivexus_original_updater/core/error/failures.dart';

/// Handles sending and receiving Android [Intent]s via a [MethodChannel].
///
/// On non-Android platforms every method returns a [Left] with an
/// [IntentFailure] explaining that the feature is unavailable, so callers can
/// gracefully degrade without runtime crashes.
class AndroidIntentHandler {
  AndroidIntentHandler({MethodChannel? channel})
      : _channel = channel ??
            const MethodChannel('com.aiorchestrator/android_intents');

  final MethodChannel _channel;

  // ── Outgoing Intents ────────────────────────────────────────────────────────

  /// Broadcasts the current project context to other apps via a custom Action.
  ///
  /// [context] — serialised context string (JSON or plain text).
  Future<Either<Failure, bool>> shareContext(String context) async {
    try {
      await _channel.invokeMethod<void>('shareContext', {'context': context});
      return const Right(true);
    } on MissingPluginException {
      return const Left(
          IntentFailure('Android Intents not available on this platform'));
    } on PlatformException catch (e) {
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  /// Sends a code snippet to another app (e.g. an IDE plugin) via Intent.
  Future<Either<Failure, bool>> sendCodeSnippet(String snippet) async {
    try {
      await _channel.invokeMethod<void>('sendCodeSnippet', {'snippet': snippet});
      return const Right(true);
    } on MissingPluginException {
      return const Left(
          IntentFailure('Android Intents not available on this platform'));
    } on PlatformException catch (e) {
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  /// Opens the Android installer sheet for the APK located at [apkPath].
  ///
  /// This only prepares and launches the install intent; user confirmation is
  /// still required by the Android package installer UI.
  Future<Either<Failure, bool>> openApkInstaller(String apkPath) async {
    try {
      debugPrint('[INSTALL] Requesting openApkInstaller for path=$apkPath');
      final result = await _channel
          .invokeMethod<bool>('openApkInstaller', {'apkPath': apkPath});
      debugPrint('[INSTALL] openApkInstaller returned ${result ?? false}');
      return Right(result ?? false);
    } on MissingPluginException {
      return const Left(
          IntentFailure('Android Intents not available on this platform'));
    } on PlatformException catch (e) {
      debugPrint('[INSTALL] openApkInstaller PlatformException: ${e.message}');
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  /// Opens Android's share sheet for a verified APK.
  ///
  /// The native side exposes a private artifact through FileProvider and
  /// stages a readable cache copy. [displayName] affects only the shared
  /// filename, not the verified APK bytes.
  Future<Either<Failure, bool>> shareApk(
    String apkPath, {
    String? displayName,
  }) async {
    try {
      final result = await _channel.invokeMethod<bool>(
        'shareApk',
        <String, Object?>{
          'apkPath': apkPath,
          if (displayName != null) 'displayName': displayName,
        },
      );
      return Right(result ?? false);
    } on MissingPluginException {
      return const Left(
        IntentFailure('Android Intents not available on this platform'),
      );
    } on PlatformException catch (e) {
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  Future<Either<Failure, bool>> openUnknownAppsSettings() async {
    try {
      debugPrint('[INSTALL] Requesting unknown-apps settings screen');
      final result = await _channel.invokeMethod<bool>('openUnknownAppsSettings');
      return Right(result ?? false);
    } on MissingPluginException {
      return const Left(
        IntentFailure('Android Intents not available on this platform'),
      );
    } on PlatformException catch (e) {
      debugPrint('[INSTALL] openUnknownAppsSettings PlatformException: ${e.message}');
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  Future<Either<Failure, Map<String, dynamic>>> getInstallDiagnostics() async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>(
        'getInstallDiagnostics',
      );
      if (result == null) {
        return const Right(<String, dynamic>{});
      }
      return Right(Map<String, dynamic>.from(result));
    } on MissingPluginException {
      return const Left(
        IntentFailure('Android Intents not available on this platform'),
      );
    } on PlatformException catch (e) {
      debugPrint('[INSTALL] getInstallDiagnostics PlatformException: ${e.message}');
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  Future<Either<Failure, Map<String, dynamic>>> verifyApk(String apkPath) async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>(
        'verifyApk',
        {'apkPath': apkPath},
      );
      if (result == null) {
        return const Right(<String, dynamic>{});
      }
      return Right(Map<String, dynamic>.from(result));
    } on MissingPluginException {
      return const Left(
        IntentFailure('Android Intents not available on this platform'),
      );
    } on PlatformException catch (e) {
      debugPrint('[INSTALL] verifyApk PlatformException: ${e.message}');
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  // ── Incoming Intents ────────────────────────────────────────────────────────

  /// Retrieves the payload forwarded from an incoming Intent, if any.
  ///
  /// Returns [Right(null)] when the app was not started via an Intent.
  Future<Either<Failure, Map<String, dynamic>?>> getIncomingIntentData() async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>(
          'getIncomingIntentData');
      return Right(result);
    } on MissingPluginException {
      return const Left(
          IntentFailure('Android Intents not available on this platform'));
    } on PlatformException catch (e) {
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  /// Requests Android package installer to open a local APK file path.
  ///
  /// Returns [Right(true)] when the install intent has been launched.
  Future<Either<Failure, bool>> installApk(String apkPath) async {
    try {
      await _channel.invokeMethod<void>('installApk', {'apkPath': apkPath});
      return const Right(true);
    } on MissingPluginException {
      return const Left(
          IntentFailure('Android Intents not available on this platform'));
    } on PlatformException catch (e) {
      return Left(IntentFailure(e.message ?? 'PlatformException'));
    }
  }

  /// Returns the custom action constant for sharing context, matching the
  /// value declared in [AndroidManifest.xml].
  static String get shareContextAction =>
      AppConstants.intentActionShareContext;

  /// Returns the custom action constant for receiving code, matching the
  /// value declared in [AndroidManifest.xml].
  static String get receiveCodeAction => AppConstants.intentActionReceiveCode;
}
