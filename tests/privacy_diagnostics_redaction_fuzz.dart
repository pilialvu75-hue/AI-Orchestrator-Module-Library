// Deterministic security regression; evidence only, not independent approval.
// Outside the pinned module payload so previous CI source digests stay valid.
import 'dart:math';
import '../intake/diagnostics.logging.library.privacy_events/0.1.0/payload/src/lib/privacy_diagnostic_events.dart';

void check(bool ok, String why) {
  if (!ok) throw StateError('privacy-diagnostics regression: $why');
}

void main() {
  const allowed = <String>{
    'stage', 'backend', 'platform', 'result', 'error_code',
    'duration_ms', 'token_count', 'bytes_total', 'bytes_done',
    'attempt_count', 'context_tokens', 'cache_hit', 'offline', 'cancelled',
  };
  const enums = <String, Set<String>>{
    'stage': {'load', 'prefill', 'decode', 'download', 'verify',
              'review', 'validate', 'apply', 'idle'},
    'backend': {'cpu', 'vulkan', 'metal', 'cuda', 'cloud', 'unknown'},
    'platform': {'android', 'ios', 'linux', 'macos', 'windows', 'web',
                 'raspberry_pi', 'unknown'},
    'result': {'success', 'failure', 'cancelled', 'degraded', 'skipped'},
    'error_code': {'NONE', 'TIMEOUT', 'OUT_OF_MEMORY', 'CANCELLED',
                   'MODEL_NOT_FOUND', 'VALIDATION_FAILED', 'HTTP_429',
                   'NATIVE_FAILURE', 'UNKNOWN'},
  };
  const metrics = <String>{
    'duration_ms', 'token_count', 'bytes_total', 'bytes_done',
    'attempt_count', 'context_tokens',
  };
  const flags = <String>{'cache_hit', 'offline', 'cancelled'};
  const maxMetric = 1125899906842624;
  final random = Random(0xA1C0DE);
  const iterations = 4096;
  for (var i = 0; i < iterations; i++) {
    final secret = 'sensitive-PROMPT-$i-private-token-${random.nextInt(1 << 30)}';
    final raw = <String, Object?>{
      'prompt': secret,
      'api_key': secret,
      'authorization': 'Bearer $secret',
      'user_id': 'patient-$secret',
      'file_path': '/home/$secret/private.gguf',
      'model_name': secret,
      'error_message': secret,
      'stage': i.isEven ? 'decode' : secret,
      'backend': i % 3 == 0 ? 'cpu' : secret,
      'platform': i % 5 == 0 ? 'windows' : secret,
      'result': i % 7 == 0 ? 'success' : secret,
      'error_code': i % 11 == 0 ? 'NONE' : secret,
      'duration_ms': i % 4 == 0 ? i : -i - 1,
      'token_count': i % 5 == 0 ? maxMetric + 1 : i,
      'bytes_total': i * 1024,
      'bytes_done': i.isEven ? i : secret,
      'attempt_count': i.isEven ? i : 1.5,
      'context_tokens': null,
      'cache_hit': i.isEven ? true : secret,
      'offline': i.isOdd,
      'cancelled': i % 3 == 0 ? false : secret,
      'untrusted_object': {'nested_secret': secret},
    };
    final event = PrivacyDiagnosticEvent(
      eventCode: 'LOCAL_INFERENCE',
      severity: 'info',
      timestamp: DateTime.utc(2026, 10, 21, 8, 0, i % 60),
      fields: raw,
    );
    final map = event.toMap();
    final fields = map['fields'] as Map<String, Object>;
    check(event.timestampUtc.isUtc, 'timestamp not UTC $i');
    check(fields.keys.every(allowed.contains), 'unknown key emitted $i');
    check(!map.toString().contains(secret), 'secret escaped $i');
    for (final entry in fields.entries) {
      final key = entry.key;
      final value = entry.value;
      if (metrics.contains(key)) {
        check(value is int && value >= 0 && value <= maxMetric,
              'unsafe metric $key at iteration $i');
      } else if (flags.contains(key)) {
        check(value is bool, 'unsafe flag $key at iteration $i');
      } else {
        check(enums.containsKey(key) &&
              value is String && enums[key]!.contains(value),
              'unsafe label $key at iteration $i');
      }
    }
    final before = map.toString();
    raw['bytes_total'] = 9999999;
    raw['stage'] = secret;
    check(map.toString() == before, 'unsafe alias of input $i');
    var immutable = false;
    try {
      fields['token_count'] = 0;
    } on UnsupportedError {
      immutable = true;
    }
    check(immutable, 'mutable output at iteration $i');
  }
  print('PASS: $iterations deterministic privacy redaction inputs; '
        'not a security certification');
}
