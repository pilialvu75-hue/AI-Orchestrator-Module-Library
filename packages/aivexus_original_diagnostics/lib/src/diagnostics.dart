import 'dart:async';

import 'package:flutter/foundation.dart';
import '../core/runtime/inference/runtime_event_log.dart';

/// Fixed vocabulary: never pass arbitrary exception text, prompts, file paths,
/// tokens, account identifiers or domain data to the persisted log.
enum DiagnosticComponent { application, updater, storage, notifications, runtime }
enum DiagnosticEvent { started, completed, failed, timeout, crash, recovered }

class AivexusDiagnostics {
  AivexusDiagnostics._();
  static final instance = AivexusDiagnostics._();
  final _log = RuntimeEventLog.instance;
  Future<void> initialize() => _log.initPersistence();
  List<RuntimeEventEntry> get entries => _log.entries;
  Stream<RuntimeEventEntry> get events => _log.stream;
  Future<String> readLocalHistory() => _log.readPersistedLog();

  void record(DiagnosticComponent component, DiagnosticEvent event, {int? elapsedMs}) {
    final duration = elapsedMs != null && elapsedMs >= 0 && elapsedMs <= 86400000
        ? ' elapsed_ms=$elapsedMs' : '';
    _log.emit('[AIVEXUS_DIAGNOSTIC] component=${component.name} event=${event.name}$duration');
  }

  /// Chain the host's Flutter error handler; no exception text or stack trace
  /// enters this module. Native crash markers are retained by the disk sink.
  VoidCallback attachFlutterErrorCapture() {
    final previous = FlutterError.onError;
    void handler(FlutterErrorDetails details) {
      record(DiagnosticComponent.application, DiagnosticEvent.crash);
      previous?.call(details);
    }
    FlutterError.onError = handler;
    return () {
      if (identical(FlutterError.onError, handler)) FlutterError.onError = previous;
    };
  }

  Future<void> clear() async {
    _log.clear();
    await _log.clearPersistedLog();
  }
}
