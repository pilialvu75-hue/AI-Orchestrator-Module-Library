/// Pure-Dart diagnostic events built from a closed vocabulary of safe values.
///
/// There is deliberately no API for free-text messages, prompts, paths,
/// tokens, user identifiers or unclassified string values. Unrecognized
/// fields are silently dropped, never retained for deferred serialization.
final class PrivacyDiagnosticEvent {
  static const Set<String> _events = {
    'MODEL_LOAD', 'MODEL_DOWNLOAD', 'LOCAL_INFERENCE',
    'DIAGNOSTIC_STALL', 'WORKSHOP_TASK', 'MODULE_VALIDATE',
  };
  static const Set<String> _severities = {'debug', 'info', 'warning', 'error'};
  static const Set<String> _countKeys = {
    'duration_ms', 'token_count', 'bytes_total', 'bytes_done',
    'attempt_count', 'context_tokens',
  };
  static const Set<String> _flagKeys = {'cache_hit', 'offline', 'cancelled'};
  static const Map<String, Set<String>> _labels = {
    'stage': {
      'load', 'prefill', 'decode', 'download', 'verify',
      'review', 'validate', 'apply', 'idle',
    },
    'backend': {'cpu', 'vulkan', 'metal', 'cuda', 'cloud', 'unknown'},
    'platform': {
      'android', 'ios', 'linux', 'macos', 'windows',
      'web', 'raspberry_pi', 'unknown',
    },
    'result': {'success', 'failure', 'cancelled', 'degraded', 'skipped'},
    'error_code': {
      'NONE', 'TIMEOUT', 'OUT_OF_MEMORY', 'CANCELLED',
      'MODEL_NOT_FOUND', 'VALIDATION_FAILED', 'HTTP_429',
      'NATIVE_FAILURE', 'UNKNOWN',
    },
  };
  static const int _maxMetric = 1125899906842624; // 1 PiB or bounded count

  final String eventCode;
  final String severity;
  final DateTime timestampUtc;
  final Map<String, Object> fields;

  PrivacyDiagnosticEvent({
    required this.eventCode,
    required this.severity,
    required DateTime timestamp,
    Map<String, Object?> fields = const {},
  })  : timestampUtc = timestamp.toUtc(),
        fields = Map.unmodifiable(_safeFields(fields)) {
    if (!_events.contains(eventCode)) {
      throw ArgumentError.value(eventCode, 'eventCode', 'unrecognized event');
    }
    if (!_severities.contains(severity)) {
      throw ArgumentError.value(severity, 'severity', 'unrecognized severity');
    }
  }

  /// Return the entire permissible event representation. No raw input map
  /// escapes and returned maps cannot be mutated by a downstream transport.
  Map<String, Object> toMap() => Map.unmodifiable({
        'schema': 'ai-orchestrator.privacy-diagnostic-event.v1',
        'event': eventCode,
        'severity': severity,
        'timestamp': timestampUtc.toIso8601String(),
        'fields': fields,
      });

  static Map<String, Object> _safeFields(Map<String, Object?> raw) {
    final selected = <String, Object>{};
    final keys = raw.keys.toList()..sort();
    for (final key in keys) {
      final value = raw[key];
      if (_countKeys.contains(key)) {
        if (value is int && value >= 0 && value <= _maxMetric) {
          selected[key] = value;
        }
      } else if (_flagKeys.contains(key)) {
        if (value is bool) selected[key] = value;
      } else {
        final validLabels = _labels[key];
        if (validLabels != null && value is String &&
            validLabels.contains(value)) {
          selected[key] = value;
        }
      }
    }
    return selected;
  }
}
