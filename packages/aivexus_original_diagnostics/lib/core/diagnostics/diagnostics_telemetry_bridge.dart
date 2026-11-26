import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:aivexus_original_diagnostics/core/app_health/contracts/abstract_telemetry_service.dart';
import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_event_log.dart';

/// Promotes a deliberately small subset of local Diagnostics events to the
/// configured telemetry backend.
///
/// RuntimeEventLog remains the source of truth and keeps working completely
/// offline. This bridge is a best-effort remote mirror for selected health
/// signals only. It never forwards the raw diagnostic message.
final class DiagnosticsTelemetryBridge {
  DiagnosticsTelemetryBridge._();

  static final DiagnosticsTelemetryBridge instance =
      DiagnosticsTelemetryBridge._();

  static const Duration _duplicateCooldown = Duration(seconds: 20);
  static const int _maxPromotionsPerMinute = 60;

  StreamSubscription<RuntimeEventEntry>? _subscription;
  AbstractTelemetryService? _telemetry;
  final Map<String, DateTime> _lastPromotionByFingerprint = <String, DateTime>{};
  final List<DateTime> _recentPromotions = <DateTime>[];

  bool get isStarted => _subscription != null;

  /// Starts the bridge once for the process lifetime.
  ///
  /// Calling [start] again replaces the current subscription, which keeps
  /// hot-restart/tests deterministic without creating duplicate uploads.
  void start({
    required AbstractTelemetryService telemetry,
    Stream<RuntimeEventEntry>? stream,
  }) {
    _telemetry = telemetry;
    unawaited(_subscription?.cancel());
    _subscription = (stream ?? RuntimeEventLog.instance.stream).listen(
      _handleEntry,
      onError: (Object error, StackTrace stackTrace) {
        // Diagnostics/telemetry must never become an app failure source.
        debugPrint(
          '[DiagnosticsTelemetryBridge] stream error '
          'type=${error.runtimeType}',
        );
      },
    );
  }

  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
    _telemetry = null;
    _lastPromotionByFingerprint.clear();
    _recentPromotions.clear();
  }

  void _handleEntry(RuntimeEventEntry entry) {
    final promotion = DiagnosticsTelemetryPolicy.promote(entry);
    if (promotion == null) return;

    final now = DateTime.now();
    _recentPromotions.removeWhere(
      (timestamp) => now.difference(timestamp) >= const Duration(minutes: 1),
    );
    if (_recentPromotions.length >= _maxPromotionsPerMinute) {
      return;
    }

    final previous = _lastPromotionByFingerprint[promotion.fingerprint];
    if (previous != null && now.difference(previous) < _duplicateCooldown) {
      return;
    }

    _lastPromotionByFingerprint[promotion.fingerprint] = now;
    _recentPromotions.add(now);

    try {
      _telemetry?.logEvent(
        promotion.eventName,
        parameters: promotion.properties,
      );
    } catch (error) {
      // The concrete telemetry service is already fail-safe, but the bridge
      // also guards this boundary so Diagnostics can never break runtime flow.
      debugPrint(
        '[DiagnosticsTelemetryBridge] promotion failed '
        'type=${error.runtimeType}',
      );
    }
  }
}

@immutable
final class DiagnosticsTelemetryPromotion {
  const DiagnosticsTelemetryPromotion({
    required this.eventName,
    required this.fingerprint,
    required this.properties,
  });

  final String eventName;
  final String fingerprint;
  final Map<String, Object> properties;
}

/// Pure privacy and promotion policy for Diagnostics -> remote telemetry.
///
/// Rules:
/// - raw [RuntimeEventEntry.message] is never exported;
/// - only closed-vocabulary strings and numeric metrics are extracted;
/// - session/model/file/user identifiers are never parsed or forwarded;
/// - normal high-frequency token/stream chatter stays local;
/// - failures/timeouts/stalls plus a few key latency metrics are promoted.
final class DiagnosticsTelemetryPolicy {
  DiagnosticsTelemetryPolicy._();

  static const Set<String> _performanceTags = <String>{
    'FIRST_TOKEN_REAL',
    'GENERATION_END',
    'KV_CACHE_REUSE',
  };

  static const Set<String> _alwaysPromoteTags = <String>{
    'NATIVE_MODEL_LOAD_FAILURE',
    'NATIVE_CONTEXT_FAILURE',
    'FIRST_TOKEN_TIMEOUT',
    'FIRST_TOKEN_DEADLINE_EXTENDED',
    'STREAM_TIMEOUT',
    'STALL',
    'WEBSEARCH_HTTP_TIMEOUT',
    'WEBSEARCH_PROVIDER_FALLBACK',
    'ANDROID_PROCESS_EXIT_UNAVAILABLE',
    'RUNTIME_FAILURE_DIAGNOSTIC',
  };

  static const Map<String, Set<String>> _safeEnumValues =
      <String, Set<String>>{
    'action': <String>{
      'attempt',
      'fallback',
      'search',
      'skip',
      'success',
    },
    'backend': <String>{
      'cpu',
      'vulkan',
      'gpu',
      'unknown',
    },
    'cost': <String>{
      'free',
      'free_tier',
      'paid',
      'unknown',
    },
    'decision': <String>{
      'attempt',
      'failure',
      'fallback',
      'skip',
      'success',
    },
    'mode': <String>{
      'cloud',
      'hybrid',
      'local',
      'offline',
      'online',
    },
    'phase': <String>{
      'idle',
      'loading',
      'running',
      'streaming',
      'completed',
      'failed',
    },
    'provider': <String>{
      'claude',
      'copilot',
      'custom',
      'duckduckgo',
      'duckduckgo_lite',
      'gemini',
      'groq',
      'grok',
      'mistral',
      'nvidia_nim',
      'openai',
      'openrouter',
      'other',
    },
    'reason': <String>{
      'authentication',
      'base_prompt_exceeds_context',
      'completed',
      'context_trim_exhausted',
      'dispatch',
      'empty_output',
      'incomplete_output',
      'network',
      'other',
      'primary_error',
      'provider_unavailable',
      'quota',
      'rate_limit',
      'timeout',
      'unsupported',
    },
    'runtime': <String>{
      'android_ffi',
      'desktop_process',
      'unknown',
    },
    'stage': <String>{
      'prompt_budget',
      'unknown',
    },
    'status': <String>{
      'cancelled',
      'completed',
      'error',
      'failed',
      'failure',
      'ffi_missing',
      'model_missing',
      'ready',
      'runtime_unavailable',
      'stalled',
      'success',
      'timed_out',
      'timeout',
      'unavailable',
    },
    'target': <String>{
      'assistant',
      'cantiere',
      'cloud',
      'local',
      'runtime',
      'search',
      'voice',
      'web',
    },
  };

  static const Set<String> _safeNumericKeys = <String>{
    'context_capacity',
    'elapsed_ms',
    'first_token_ms',
    'generation_reserve',
    'n_batch',
    'n_ctx',
    'n_threads',
    'requested_layers',
    'reused_tokens',
    'prefilled_tokens',
    'prompt_tokens',
    'max_prompt_tokens',
    'requested_max_tokens',
    'safety_margin',
    'trimmed_turns',
    'token_index',
    'tokens',
    'tokens_generated',
  };

  static final RegExp _keyValueRegExp = RegExp(
    r'(?:^|\s)([a-zA-Z][a-zA-Z0-9_]*)=([^\s]+)',
  );

  static final RegExp _problemTagRegExp = RegExp(
    r'(?:ERROR|FAIL|FAILED|FAILURE|TIMEOUT|STALL|CRASH|BLOCKED|UNAVAILABLE|OOM)',
  );

  @visibleForTesting
  static DiagnosticsTelemetryPromotion? promote(RuntimeEventEntry entry) {
    final tag = entry.tag.toUpperCase();

    if (tag == 'FORENSIC_UNCAUGHT_DART_EXCEPTION') {
      // Already routed through AbstractTelemetryService.logCrash in main.dart.
      return null;
    }

    if (tag == 'AI_RUNTIME_MONITOR') {
      return _runtimeMonitorPromotion(entry);
    }

    if (tag == 'CLOUD_ROUTING') {
      final safe = _extractSafeProperties(entry.message);
      if (safe['decision'] != 'failure') return null;
      return _buildIssuePromotion(entry, safe);
    }

    if (_performanceTags.contains(tag)) {
      final safe = _extractSafeProperties(entry.message);
      final hasLatencyMetric =
          safe.containsKey('elapsed_ms') || safe.containsKey('first_token_ms');
      final hasKvReuseMetrics =
          tag == 'KV_CACHE_REUSE' &&
          safe.containsKey('reused_tokens') &&
          safe.containsKey('prefilled_tokens');
      if (!hasLatencyMetric && !hasKvReuseMetrics) {
        return null;
      }
      return DiagnosticsTelemetryPromotion(
        eventName: 'diagnostic_performance',
        fingerprint: 'performance:$tag',
        properties: <String, Object>{
          'diagnostic_tag': tag,
          'category': entry.category.name,
          ...safe,
        },
      );
    }

    if (!_alwaysPromoteTags.contains(tag) &&
        !_problemTagRegExp.hasMatch(tag)) {
      return null;
    }

    return _buildIssuePromotion(
      entry,
      _extractSafeProperties(entry.message),
    );
  }

  static DiagnosticsTelemetryPromotion? _runtimeMonitorPromotion(
    RuntimeEventEntry entry,
  ) {
    final message = entry.message;
    final arrow = RegExp(
      r'\[AI_RUNTIME_MONITOR\]\s+([A-Za-z]+)\s+->\s+([A-Za-z]+)',
    ).firstMatch(message);
    if (arrow == null) return null;

    final previous = arrow.group(1);
    final current = arrow.group(2);
    if (previous == null || current == null) return null;

    const problemStates = <String>{
      'failed',
      'timedOut',
      'stalled',
      'ffiMissing',
      'modelMissing',
      'runtimeUnavailable',
    };
    if (!problemStates.contains(current)) return null;

    final safe = _extractSafeProperties(message);
    return DiagnosticsTelemetryPromotion(
      eventName: 'diagnostic_issue',
      fingerprint: 'AI_RUNTIME_MONITOR:$current',
      properties: <String, Object>{
        'diagnostic_tag': 'AI_RUNTIME_MONITOR',
        'category': entry.category.name,
        'severity': current == 'failed' ? 'error' : 'warning',
        'previous_status': _normalizeEnum(previous),
        'status': _normalizeEnum(current),
        ...safe,
      },
    );
  }

  static DiagnosticsTelemetryPromotion _buildIssuePromotion(
    RuntimeEventEntry entry,
    Map<String, Object> safe,
  ) {
    final tag = entry.tag.toUpperCase();
    final severity = _severityFor(tag);
    final reason = safe['reason']?.toString();
    final status = safe['status']?.toString();
    final discriminator = reason ?? status ?? severity;

    return DiagnosticsTelemetryPromotion(
      eventName: 'diagnostic_issue',
      fingerprint: '$tag:$discriminator',
      properties: <String, Object>{
        'diagnostic_tag': tag,
        'category': entry.category.name,
        'severity': severity,
        ...safe,
      },
    );
  }

  static Map<String, Object> _extractSafeProperties(String message) {
    final safe = <String, Object>{};
    for (final match in _keyValueRegExp.allMatches(message)) {
      final key = match.group(1)?.toLowerCase();
      final rawValue = match.group(2);
      if (key == null || rawValue == null) continue;

      if (_safeNumericKeys.contains(key)) {
        final normalized = rawValue.replaceAll(RegExp(r'[^0-9.-]'), '');
        final value = num.tryParse(normalized);
        if (value != null) safe[key] = value;
        continue;
      }

      final allowedValues = _safeEnumValues[key];
      if (allowedValues != null) {
        final normalized = _normalizeEnum(rawValue);
        if (allowedValues.contains(normalized)) {
          safe[key] = normalized;
        } else if (key == 'provider') {
          safe[key] = 'other';
        }
      }
    }
    return safe;
  }

  static String _normalizeEnum(String value) {
    return value
        .trim()
        .replaceAll(RegExp(r'[^a-zA-Z0-9_.:-]'), '_')
        .toLowerCase();
  }

  static String _severityFor(String tag) {
    if (tag.contains('CRASH') ||
        tag.contains('OOM') ||
        tag.contains('FAILURE') ||
        tag.contains('FAILED') ||
        tag.contains('ERROR')) {
      return 'error';
    }
    return 'warning';
  }
}
