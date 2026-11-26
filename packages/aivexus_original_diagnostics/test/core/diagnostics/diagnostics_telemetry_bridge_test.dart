import 'package:flutter_test/flutter_test.dart';

import 'package:aivexus_original_diagnostics/core/diagnostics/diagnostics_telemetry_bridge.dart';
import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_event_log.dart';

RuntimeEventEntry _entry(
  String tag,
  String message, {
  RuntimeEventCategory category = RuntimeEventCategory.other,
}) {
  return RuntimeEventEntry(
    timestamp: DateTime(2026, 9, 21),
    category: category,
    tag: tag,
    message: message,
  );
}

void main() {
  group('DiagnosticsTelemetryPolicy', () {
    test('promotes runtime failure without forwarding free-form message', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'AI_RUNTIME_MONITOR',
          '[AI_RUNTIME_MONITOR] ready -> failed '
          'tokens=17 elapsed_ms=9000 '
          'message="private local path / secret prompt"',
          category: RuntimeEventCategory.runtime,
        ),
      );

      expect(promotion, isNotNull);
      expect(promotion!.eventName, 'diagnostic_issue');
      expect(promotion.properties['diagnostic_tag'], 'AI_RUNTIME_MONITOR');
      expect(promotion.properties['status'], 'failed');
      expect(promotion.properties['tokens'], 17);
      expect(promotion.properties['elapsed_ms'], 9000);
      expect(
        promotion.properties.values.join(' '),
        isNot(contains('private local path')),
      );
      expect(
        promotion.properties.values.join(' '),
        isNot(contains('secret prompt')),
      );
    });

    test('promotes bounded runtime failure evidence without raw message', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'RUNTIME_FAILURE_DIAGNOSTIC',
          '[RUNTIME_FAILURE_DIAGNOSTIC] stage=prompt_budget '
          'reason=base_prompt_exceeds_context runtime=android_ffi '
          'context_capacity=2048 prompt_tokens=1730 requested_max_tokens=512 '
          'generation_reserve=0 safety_margin=64 secret=private',
          category: RuntimeEventCategory.inference,
        ),
      );

      expect(promotion, isNotNull);
      expect(promotion!.properties['stage'], 'prompt_budget');
      expect(promotion.properties['reason'], 'base_prompt_exceeds_context');
      expect(promotion.properties['runtime'], 'android_ffi');
      expect(promotion.properties['context_capacity'], 2048);
      expect(promotion.properties['prompt_tokens'], 1730);
      expect(promotion.properties['requested_max_tokens'], 512);
      expect(promotion.properties['generation_reserve'], 0);
      expect(promotion.properties['safety_margin'], 64);
      expect(promotion.properties, isNot(contains('secret')));
      expect(promotion.properties.values.join(' '), isNot(contains('private')));
    });

    test('promotes context-trim exhaustion metrics', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'RUNTIME_FAILURE_DIAGNOSTIC',
          '[RUNTIME_FAILURE_DIAGNOSTIC] stage=prompt_budget '
          'reason=context_trim_exhausted runtime=android_ffi '
          'context_capacity=2048 prompt_tokens=1990 max_prompt_tokens=1472 '
          'requested_max_tokens=512 generation_reserve=512 safety_margin=64 '
          'trimmed_turns=4',
          category: RuntimeEventCategory.inference,
        ),
      );

      expect(promotion, isNotNull);
      expect(promotion!.properties['reason'], 'context_trim_exhausted');
      expect(promotion.properties['max_prompt_tokens'], 1472);
      expect(promotion.properties['trimmed_turns'], 4);
    });

    test('keeps normal runtime transitions local only', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'AI_RUNTIME_MONITOR',
          '[AI_RUNTIME_MONITOR] loading -> ready tokens=0 elapsed_ms=1200',
          category: RuntimeEventCategory.runtime,
        ),
      );

      expect(promotion, isNull);
    });

    test('promotes cloud routing failures using closed vocabulary only', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'CLOUD_ROUTING',
          '[CLOUD_ROUTING] task=coding cost=free provider=mistral '
          'decision=failure reason=rate_limit prompt="never export me"',
        ),
      );

      expect(promotion, isNotNull);
      expect(promotion!.properties['decision'], 'failure');
      expect(promotion.properties['reason'], 'rate_limit');
      expect(promotion.properties['provider'], 'mistral');
      expect(promotion.properties, isNot(contains('prompt')));
      expect(
        promotion.properties.values.join(' '),
        isNot(contains('never export me')),
      );
    });

    test('does not duplicate uncaught exceptions already sent as crashes', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'FORENSIC_UNCAUGHT_DART_EXCEPTION',
          '[FORENSIC_UNCAUGHT_DART_EXCEPTION] message=secret',
        ),
      );

      expect(promotion, isNull);
    });

    test('promotes first-token latency without identifiers or text', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'FIRST_TOKEN_REAL',
          '[FIRST_TOKEN_REAL] elapsed_ms=27500 session=private123 '
          'model_path=/storage/private.gguf',
          category: RuntimeEventCategory.inference,
        ),
      );

      expect(promotion, isNotNull);
      expect(promotion!.eventName, 'diagnostic_performance');
      expect(promotion.properties['elapsed_ms'], 27500);
      expect(promotion.properties, isNot(contains('session')));
      expect(promotion.properties, isNot(contains('model_path')));
    });

    test('promotes KV reuse counts without logical session identifiers', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'KV_CACHE_REUSE',
          '[KV_CACHE_REUSE] session=private-chat scope=logical_session '
          'reason=verified_prefix reused_tokens=820 prefilled_tokens=44 '
          'prompt_tokens=864',
          category: RuntimeEventCategory.model,
        ),
      );

      expect(promotion, isNotNull);
      expect(promotion!.eventName, 'diagnostic_performance');
      expect(promotion.properties['reused_tokens'], 820);
      expect(promotion.properties['prefilled_tokens'], 44);
      expect(promotion.properties['prompt_tokens'], 864);
      expect(promotion.properties, isNot(contains('session')));
      expect(promotion.properties, isNot(contains('scope')));
    });

    test('keeps high-frequency token chatter local', () {
      final promotion = DiagnosticsTelemetryPolicy.promote(
        _entry(
          'TOKEN_EMIT',
          '[TOKEN_EMIT] token_index=17 chars=4 session=private',
          category: RuntimeEventCategory.token,
        ),
      );

      expect(promotion, isNull);
    });
  });
}
