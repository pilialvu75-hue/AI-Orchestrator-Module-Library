import 'package:privacy_diagnostic_events/privacy_diagnostic_events.dart';

void expectTrue(bool condition, String caseName) {
  if (!condition) throw StateError('FAILED: $caseName');
}

void main() {
  final raw = <String, Object?>{
    'prompt': 'sensitive user prompt',
    'api_key': 'private credential',
    'authorization': 'Bearer secret',
    'model_path': '/user/private/models/file.gguf',
    'message': 'untrusted model output',
    'stage': 'prefill',
    'backend': 'vulkan',
    'platform': 'linux',
    'error_code': 'NONE',
    'token_count': 32,
    'duration_ms': 391,
    'bytes_total': 475271763,
    'cache_hit': false,
    'offline': true,
    'result': 'success',
    'attempt_count': -4,
  };
  final event = PrivacyDiagnosticEvent(
    eventCode: 'LOCAL_INFERENCE',
    severity: 'info',
    timestamp: DateTime.utc(2026, 10, 18, 10, 0),
    fields: raw,
  );
  final view = event.toMap();
  final fields = view['fields'] as Map<String, Object>;
  final serialized = view.toString();

  expectTrue(event.timestampUtc.isUtc, 'UTC timestamp');
  expectTrue(fields['stage'] == 'prefill', 'known enum accepted');
  expectTrue(fields['backend'] == 'vulkan', 'known backend accepted');
  expectTrue(fields['token_count'] == 32, 'numeric metric accepted');
  expectTrue(fields['bytes_total'] == 475271763, 'large model count accepted');
  expectTrue(fields['offline'] == true, 'typed flag accepted');
  expectTrue(!fields.containsKey('attempt_count'), 'negative number rejected');
  for (final secret in ['sensitive user prompt', 'private credential',
                        'Bearer secret', '/user/private/models', 'untrusted model output']) {
    expectTrue(!serialized.contains(secret), 'raw input must never escape');
  }
  expectTrue(!fields.containsKey('prompt') && !fields.containsKey('api_key'),
      'unsafe keys discarded');
  raw['token_count'] = 999;
  expectTrue(fields['token_count'] == 32, 'input alias cannot mutate emitted event');

  final invalid = PrivacyDiagnosticEvent(
    eventCode: 'MODEL_DOWNLOAD',
    severity: 'warning',
    timestamp: DateTime.utc(2026),
    fields: {'result': 'user secret', 'stage': 'private-folder',
             'token_count': 1.5, 'cache_hit': 'yes',
             'bytes_done': 1125899906842625},
  );
  expectTrue((invalid.toMap()['fields'] as Map<String, Object>).isEmpty,
      'invalid allowed-key values also discarded');

  var blockedCode = false;
  try {
    PrivacyDiagnosticEvent(
      eventCode: 'SECRET_USERNAME',
      severity: 'info',
      timestamp: DateTime.utc(2026),
    );
  } on ArgumentError {
    blockedCode = true;
  }
  expectTrue(blockedCode, 'event identifier constrained to vocabulary');

  var blockedSeverity = false;
  try {
    PrivacyDiagnosticEvent(
      eventCode: 'MODEL_LOAD',
      severity: 'secret text',
      timestamp: DateTime.utc(2026),
    );
  } on ArgumentError {
    blockedSeverity = true;
  }
  expectTrue(blockedSeverity, 'severity constrained to vocabulary');

  var immutable = false;
  try {
    event.fields['token_count'] = 99;
  } on UnsupportedError {
    immutable = true;
  }
  expectTrue(immutable, 'safe result immutable');
  print('PASS: privacy diagnostic contract, redaction, bounds and immutability');
}
