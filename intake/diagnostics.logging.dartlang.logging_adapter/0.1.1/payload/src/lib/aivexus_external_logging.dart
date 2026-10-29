import 'dart:async';

import 'package:logging/logging.dart';

/// A constrained, offline-only diagnostics.logging.v1 integration adapter.
///
/// The vendored upstream Logger is deliberately *detached*: this module does
/// not intercept other application logs, process output, or environment data.
enum AivexusSeverity { debug, info, warning, error }

/// Closed, source-reviewed vocabulary. Each new code requires a new pinned
/// module version and a fresh external security assessment. Never encode
/// prompts, filenames, user identifiers or free text in event names.
enum AivexusEventCode {
  startupReady('startup_ready'),
  localModelLoaded('local_model_loaded'),
  retryScheduled('retry_scheduled'),
  consumerStarted('consumer_started'),
  moduleConnected('module_connected');

  const AivexusEventCode(this.wireCode);
  final String wireCode;
}

class AivexusLogEntry {
  final String eventCode;
  final AivexusSeverity severity;
  final DateTime timestampUtc;

  const AivexusLogEntry(this.eventCode, this.severity, this.timestampUtc);

  Map<String, Object> toJson() => {
        'event_code': eventCode,
        'severity': severity.name,
        'timestamp_utc': timestampUtc.toIso8601String(),
      };
}

class AivexusLoggingModule {
  final Logger _logger = Logger.detached('aivexus.external');
  final int capacity;
  final List<AivexusLogEntry> _events = [];
  late final StreamSubscription<LogRecord> _subscription;
  bool _disposed = false;

  AivexusLoggingModule({this.capacity = 128}) {
    if (capacity < 1 || capacity > 4096) {
      throw RangeError.range(capacity, 1, 4096, 'capacity');
    }
    _logger.level = Level.ALL;
    _subscription = _logger.onRecord.listen((record) {
      final severity = switch (record.level.name) {
        'FINE' => AivexusSeverity.debug,
        'WARNING' => AivexusSeverity.warning,
        'SEVERE' => AivexusSeverity.error,
        _ => AivexusSeverity.info,
      };
      if (_events.length >= capacity) {
        _events.removeAt(0);
      }
      _events.add(AivexusLogEntry(
        record.message,
        severity,
        record.time.toUtc(),
      ));
    });
  }

  /// Accept only the finite AivexusEventCode vocabulary; no caller strings.
  void emit(AivexusEventCode code, {AivexusSeverity severity = AivexusSeverity.info}) {
    if (_disposed) throw StateError('logging module is disposed');
    final level = switch (severity) {
      AivexusSeverity.debug => Level.FINE,
      AivexusSeverity.info => Level.INFO,
      AivexusSeverity.warning => Level.WARNING,
      AivexusSeverity.error => Level.SEVERE,
    };
    _logger.log(level, code.wireCode);
  }

  /// No disk, network, telemetry upload or global logger side effects.
  List<AivexusLogEntry> snapshot() => List.unmodifiable(_events);

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await _subscription.cancel();
    _logger.clearListeners();
    _events.clear();
  }
}
