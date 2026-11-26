import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'diagnostics.dart';
import 'exit_history.dart';

class DiagnosticAppInfo {
  const DiagnosticAppInfo({required this.version, required this.build, required this.platform});
  final String version;
  final String build;
  final String platform;

  static Future<DiagnosticAppInfo> read() async {
    final platform = kIsWeb ? 'web' : defaultTargetPlatform.name;
    try {
      final info = await PackageInfo.fromPlatform().timeout(const Duration(seconds: 2));
      return DiagnosticAppInfo(version: _version(info.version), build: _version(info.buildNumber), platform: platform);
    } catch (_) {
      return DiagnosticAppInfo(version: 'Unavailable', build: 'Unavailable', platform: platform);
    }
  }

  static String _version(String value) {
    // Only numeric version identifiers and conventional version qualifiers.
    return RegExp(r'^[0-9][0-9.]{0,31}(?:[-+](?:dev|beta|alpha|rc|nightly|[0-9])[0-9.]{0,15})?$').hasMatch(value)
      ? value : 'Unavailable';
  }
}

/// Host-owned startup integration; no timers/network. Native history stays
/// separate from new runtime events so historical exits are never called fresh crashes.
class DiagnosticSession {
  DiagnosticSession._();
  static final instance = DiagnosticSession._();
  final exitHistory = DiagnosticExitHistory();
  Future<void>? _startup;
  VoidCallback? _detach;
  DiagnosticAppInfo? appInfo;

  Future<void> start() => _startup ??= _start();
  Future<void> _start() async {
    final diagnostics = AivexusDiagnostics.instance;
    await diagnostics.initialize();
    _detach = diagnostics.attachAutomaticErrorCapture();
    diagnostics.record(DiagnosticComponent.application, DiagnosticEvent.started);
    await Future.wait<void>([
      DiagnosticAppInfo.read().then((info) { appInfo = info; }),
      exitHistory.refresh(),
    ]);
  }

  /// Only when the host explicitly tears down the session. A mobile process
  /// can be killed without this callback; absence is not evidence of a crash.
  void detach() {
    _detach?.call();
    _detach = null;
    _startup = null;
  }
}
