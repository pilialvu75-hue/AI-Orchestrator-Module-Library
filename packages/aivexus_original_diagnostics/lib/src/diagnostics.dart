import 'dart:async';
import 'dart:ui' show PlatformDispatcher;

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
  List<RuntimeEventEntry> get entries => List.unmodifiable(_log.entries.where(isSafeEntry));
  Stream<RuntimeEventEntry> get events => _log.stream.where(isSafeEntry);
  Future<String> readLocalHistory() async {
    final safe = await readSafeHistory();
    return safe.isEmpty ? '(no retained diagnostic events)' : safe;
  }

  // Reject arbitrary text even when a caller used the internal original logger.
  static bool _safeMessage(String message) {
    final match = RegExp(r'^\[AIVEXUS_DIAGNOSTIC\] component=([a-z]+) event=([a-z]+)(?: elapsed_ms=(\d{1,8}))?$').firstMatch(message);
    if (match == null || match.end != message.length) return false;
    final elapsed = match.group(3);
    return DiagnosticComponent.values.any((c) => c.name == match.group(1)) &&
      DiagnosticEvent.values.any((e) => e.name == match.group(2)) &&
      (elapsed == null || int.parse(elapsed) <= 86400000);
  }

  static bool isSafeEntry(RuntimeEventEntry entry) =>
      entry.tag == 'AIVEXUS_DIAGNOSTIC' && _safeMessage(entry.message);

  Future<String> readSafeHistory() async {
    final raw = await _log.readPersistedLog();
    return raw.split('\n').where((line) {
      final match = RegExp(r'^\[(\d{4}-\d\d-\d\dT[\d:.+Z-]+)\] \[AIVEXUS_DIAGNOSTIC\] (.*)$').firstMatch(line);
      return match != null && match.end == line.length &&
        DateTime.tryParse(match.group(1)!) != null && _safeMessage(match.group(2)!);
    }).join('\n');
  }

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

  /// Captures framework and root-isolate unhandled errors without retaining
  /// exception or stack text. Preserves host error handling and return value.
  /// Install once after initialize(), and detach during host teardown.
  VoidCallback attachAutomaticErrorCapture() {
    final detachFlutter = attachFlutterErrorCapture();
    final dispatcher = PlatformDispatcher.instance;
    final previous = dispatcher.onError;
    bool handler(Object error, StackTrace stack) {
      record(DiagnosticComponent.application, DiagnosticEvent.crash);
      return previous?.call(error, stack) ?? false;
    }
    dispatcher.onError = handler;
    return () {
      detachFlutter();
      if (identical(dispatcher.onError, handler)) dispatcher.onError = previous;
    };
  }

  Future<void> clear() async {
    _log.clear();
    await _log.clearPersistedLog();
  }
}
