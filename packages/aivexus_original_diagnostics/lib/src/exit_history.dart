import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

enum ExitReason { nativeCrash, managedCrash, lowMemory, anr, signal, exitSelf, userRequested, other }
enum ExitHistoryStatus { unavailable, loading, available }

class DiagnosticExitRecord {
  const DiagnosticExitRecord(this.timestamp, this.reason);
  final DateTime timestamp;
  final ExitReason reason;

  static DiagnosticExitRecord? parse(Object? input, DateTime now) {
    if (input is! Map) return null;
    final milliseconds = input['timestamp_ms'];
    if (milliseconds is! int || milliseconds <= 0 ||
        milliseconds > now.millisecondsSinceEpoch) return null;
    final reason = switch (input['reason']) {
      'native_crash' => ExitReason.nativeCrash,
      'managed_crash' => ExitReason.managedCrash,
      'low_memory' => ExitReason.lowMemory,
      'anr' => ExitReason.anr,
      'signal' => ExitReason.signal,
      'exit_self' => ExitReason.exitSelf,
      'user_requested' => ExitReason.userRequested,
      _ => ExitReason.other,
    };
    return DiagnosticExitRecord(DateTime.fromMillisecondsSinceEpoch(milliseconds, isUtc: true), reason);
  }
}

/// Adapted original Android process-exit channel. A two-second timeout limits
/// startup waiting; late native records are still accepted. No description,
/// stack trace, process name, path, identifier or abort message is retained.
class DiagnosticExitHistory extends ChangeNotifier {
  DiagnosticExitHistory({Future<List<dynamic>?> Function()? reader})
      : _reader = reader ?? _platformRead;
  static const _channel = MethodChannel('com.aiorchestrator/process_exit');
  static Future<List<dynamic>?> _platformRead() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return null;
    return _channel.invokeListMethod<dynamic>('readHistory');
  }

  final Future<List<dynamic>?> Function() _reader;
  ExitHistoryStatus _status = ExitHistoryStatus.unavailable;
  ExitHistoryStatus get status => _status;
  List<DiagnosticExitRecord> _records = const [];
  List<DiagnosticExitRecord> get records => _records;
  Future<void>? _pending;
  bool _disposed = false;

  Future<void> refresh() async {
    if (_disposed) return;
    if (_pending == null) {
      _status = ExitHistoryStatus.loading;
      _pending = Future<List<dynamic>?>.sync(_reader).then<void>((data) {
        if (_disposed) return;
        final now = DateTime.now();
        final unique = <String, DiagnosticExitRecord>{};
        for (final raw in (data ?? const []).take(3)) {
          final record = DiagnosticExitRecord.parse(raw, now);
          if (record != null) {
            unique['${record.timestamp.millisecondsSinceEpoch}:${record.reason.name}'] = record;
          }
        }
        final ordered = unique.values.toList()..sort((a, b) => b.timestamp.compareTo(a.timestamp));
        _records = List.unmodifiable(ordered);
        _status = data == null ? ExitHistoryStatus.unavailable : ExitHistoryStatus.available;
        notifyListeners();
      }, onError: (Object _) {
        if (_disposed) return;
        _status = ExitHistoryStatus.unavailable;
        _records = const [];
        notifyListeners();
      }).whenComplete(() { _pending = null; });
      notifyListeners();
    }
    try {
      await _pending!.timeout(const Duration(seconds: 2));
    } on TimeoutException {
      // The original continuation remains active and can deliver late history.
    }
  }
  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
