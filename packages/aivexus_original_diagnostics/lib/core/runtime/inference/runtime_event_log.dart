import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_crash_log_sink.dart';

/// Categorises a runtime log entry by the subsystem that produced it.
enum RuntimeEventCategory {
  model,
  runtime,
  inference,
  fallback,
  token,
  stream,
  validation,
  websearch,
  voice,
  hardware,
  other,
}

/// A single timestamped entry captured from the runtime inference pipeline.
class RuntimeEventEntry {
  const RuntimeEventEntry({
    required this.timestamp,
    required this.category,
    required this.tag,
    required this.message,
  });

  final DateTime timestamp;
  final RuntimeEventCategory category;

  /// First bracketed tag extracted from the log message, e.g. `[MODEL_PATH]`.
  final String tag;

  /// Full log message as emitted by the pipeline.
  final String message;

  @override
  String toString() =>
      '[${timestamp.toIso8601String()}] [$tag] $message';
}

/// Process-wide log buffer for all runtime inference events.
///
/// Providers call [emit] for every significant pipeline event. UI layers
/// listen to [stream] for live updates or read [entries] for the current
/// in-memory snapshot.
///
/// The in-memory buffer is capped at [maxEntries] to avoid unbounded
/// memory growth. When the cap is reached the oldest entry is discarded.
///
/// Every entry is also appended, synchronously and with an immediate
/// flush, to a persistent on-disk file via [RuntimeCrashLogSink]. This
/// is what lets a crash investigation see the last events even when a
/// native crash kills the process before any Dart exception handler can
/// run — the in-memory buffer alone does not survive that, the file does.
class RuntimeEventLog {
  RuntimeEventLog._();

  /// Singleton instance shared across all runtime components.
  static final RuntimeEventLog instance = RuntimeEventLog._();

  /// Maximum number of entries retained in memory.
  static const int maxEntries = 600;

  final List<RuntimeEventEntry> _entries = [];
  final StreamController<RuntimeEventEntry> _controller =
      StreamController<RuntimeEventEntry>.broadcast();

  // Separate controller used to notify listeners that the log was cleared.
  final StreamController<void> _clearController =
      StreamController<void>.broadcast();

  /// Current snapshot of all retained log entries (oldest first).
  List<RuntimeEventEntry> get entries => List.unmodifiable(_entries);

  /// Stream that emits each new [RuntimeEventEntry] as it arrives.
  Stream<RuntimeEventEntry> get stream => _controller.stream;

  /// Stream that fires whenever [clear] is called.
  Stream<void> get onClear => _clearController.stream;

  /// Prepares on-disk persistence. Must be awaited exactly once, as
  /// early as possible in `main()`, before any other runtime activity.
  ///
  /// Safe to skip: if never called, [emit] simply keeps working as an
  /// in-memory-only log, exactly as before persistence was added.
  Future<void> initPersistence() {
    return RuntimeCrashLogSink.instance.init();
  }

  /// Adds [message] to the log buffer, broadcasts it to all listeners,
  /// and persists it to disk.
  ///
  /// The category and tag are inferred automatically from the first
  /// `[TAG]` token in [message]. Sensitive legacy Web-search query fields are
  /// redacted here, before they can reach memory, listeners or disk.
  void emit(String message) {
    final safeMessage = redactSensitiveFields(message);
    final tag = _extractTag(safeMessage);
    final category = _categoryFor(tag);
    final entry = RuntimeEventEntry(
      timestamp: DateTime.now(),
      category: category,
      tag: tag,
      message: safeMessage,
    );

    if (_entries.length >= maxEntries) _entries.removeAt(0);
    _entries.add(entry);

    // Persisted before the broadcast below: if a listener reacting to
    // this event were to trigger a native call that crashes the
    // process, the line must already be safely on disk.
    RuntimeCrashLogSink.instance.append(entry.toString());

    if (!_controller.isClosed) {
      _controller.add(entry);
    }
  }

  /// Removes all retained in-memory entries and notifies listeners via
  /// [onClear]. Does NOT touch the persisted on-disk log — that history
  /// is kept for crash forensics until [clearPersistedLog] is called
  /// explicitly.
  void clear() {
    _entries.clear();

    if (!_clearController.isClosed) {
      _clearController.add(null);
    }
  }

  /// Reads the full persisted on-disk log as text, including entries
  /// from previous app runs (e.g. before a crash).
  Future<String> readPersistedLog() {
    return RuntimeCrashLogSink.instance.readAsText();
  }

  /// Erases the persisted on-disk log. Use only when the user
  /// explicitly asks to reset diagnostics.
  Future<void> clearPersistedLog() {
    return RuntimeCrashLogSink.instance.clear();
  }

  // ── Private helpers ──────────────────────────────────────────────────────────

  static final _tagRegExp = RegExp(r'^\[([A-Z0-9_]+)\]');
  static final _legacyQuotedQueryRegExp = RegExp(r'\bquery\s*=\s*"');

  /// Central privacy guard for legacy diagnostic fields carrying a complete
  /// user Web-search query.
  ///
  /// The two historical producers interpolate the query as the final
  /// `query="..."` field without escaping embedded quotes/newlines. Once that
  /// interpolation has happened there is no reliable way to identify a closing
  /// quote for every possible user query, so the safe boundary behaviour is to
  /// retain the structural prefix and redact the entire remaining query tail.
  ///
  /// Length-only fields such as `query_chars=42` deliberately remain intact.
  @visibleForTesting
  static String redactSensitiveFields(String message) {
    final match = _legacyQuotedQueryRegExp.firstMatch(message);
    if (match == null) return message;

    final assignment = message.substring(match.start, match.end);
    return '${message.substring(0, match.start)}$assignment[REDACTED]"';
  }

  static String _extractTag(String message) {
    final match = _tagRegExp.firstMatch(message.trim());
    return match?.group(1) ?? 'LOG';
  }

  static RuntimeEventCategory _categoryFor(String tag) {
    if (_modelTags.contains(tag) ||
        tag.startsWith('MODEL') ||
        tag.startsWith('GGUF') ||
        tag.startsWith('TOKENIZER') ||
        tag.startsWith('TOKEN_COUNT') ||
        tag.startsWith('TOKEN_DECODE') ||
        tag.startsWith('TOKEN_EVAL') ||
        tag.startsWith('KV_CACHE')) {
      return RuntimeEventCategory.model;
    }

    if (_runtimeTags.contains(tag) ||
        tag.startsWith('FFI') ||
        tag.startsWith('NATIVE') ||
        tag.startsWith('BOOT') ||
        tag.startsWith('WARMUP') ||
        tag.startsWith('CONTEXT') ||
        tag == 'SESSION') {
      return RuntimeEventCategory.runtime;
    }

    if (_inferenceTags.contains(tag) ||
        tag.startsWith('GENERATION') ||
        tag.startsWith('PROMPT') ||
        tag.startsWith('FIRST_TOKEN') ||
        tag == 'TERMINAL_STATE' ||
        tag == 'INFERENCE' ||
        tag.startsWith('STALL') ||
        tag == 'STREAM_TIMEOUT' ||
        tag == 'STREAM_LOOP') {
      return RuntimeEventCategory.inference;
    }

    if (_fallbackTags.contains(tag) ||
        tag.startsWith('FALLBACK') ||
        tag == 'RUNTIME_PATH') {
      return RuntimeEventCategory.fallback;
    }

    if (tag.startsWith('WEBSEARCH')) {
      return RuntimeEventCategory.websearch;
    }

    if (tag.startsWith('VOICE') || tag.startsWith('TTS')) {
      return RuntimeEventCategory.voice;
    }

    if (tag.startsWith('GPU') || tag.startsWith('HARDWARE') || tag.startsWith('RESOURCE_')) {
      return RuntimeEventCategory.hardware;
    }

    if (_tokenTags.contains(tag) ||
        tag.startsWith('TOKEN_STREAM') ||
        tag.startsWith('TOKEN_LOOP') ||
        tag.startsWith('TOKEN_EMIT') ||
        tag.startsWith('DART_TOKEN') ||
        tag.startsWith('DART_STREAM_RECEIVE') ||
        tag.startsWith('DART_STREAM_RENDER')) {
      return RuntimeEventCategory.token;
    }

    if (_streamTags.contains(tag) ||
        tag.startsWith('STREAM') ||
        tag.startsWith('FINAL_RESPONSE') ||
        tag.startsWith('DART_STREAM_CLOSE') ||
        tag.startsWith('DART_STREAM_LISTEN')) {
      return RuntimeEventCategory.stream;
    }

    if (_validationTags.contains(tag) ||
        tag.startsWith('VALIDATION') ||
        tag.startsWith('MODEL_EXISTS') ||
        tag.startsWith('MODEL_SIZE') ||
        tag.startsWith('MODEL_READABLE') ||
        tag.startsWith('MODEL_PATH')) {
      return RuntimeEventCategory.validation;
    }

    return RuntimeEventCategory.other;
  }

  // Pre-defined tag sets for exact matches to avoid prefix collisions.
  static const Set<String> _modelTags = {
    'MODEL',
    'GGUF',
    'TOKENIZER',
    'TOKENIZER_OK',
    'TOKENIZER_DECODE_FAIL',
    'TOKEN_COUNT',
    'KV_CACHE',
    'TOKEN_EVAL',
    'TOKEN_DECODE',
    'CONTEXT_SIZE',
    'MODEL_EXECUTION',
  };

  static const Set<String> _runtimeTags = {
    'RUNTIME',
    'FFI_INIT',
    'SESSION',
    'BOOT',
    'WARMUP',
    'NATIVE_MODEL_LOAD_BEGIN',
    'NATIVE_MODEL_LOAD_RESULT',
    'NATIVE_MODEL_LOAD_SUCCESS',
    'NATIVE_MODEL_LOAD_FAILURE',
    'NATIVE_CONTEXT_CREATE',
    'NATIVE_CONTEXT_FAILURE',
    'CONTEXT',
    'DART_THREAD',
  };

  static const Set<String> _inferenceTags = {
    'INFERENCE',
    'GENERATION_START',
    'GENERATION_END',
    'GENERATION_ALIVE',
    'GENERATION_STEP',
    'GENERATION_IDLE',
    'GENERATION_ERROR',
    'TERMINAL_STATE',
    'FIRST_TOKEN_REAL',
    'FIRST_TOKEN_WAIT',
    'FIRST_TOKEN_TIMEOUT',
    'FIRST_TOKEN_DEADLINE_EXTENDED',
    'FIRST_TOKEN',
    'STALL',
    'STREAM_TIMEOUT',
    'STREAM_LOOP',
    'PROMPT_EVAL',
    'ORCHESTRATOR_BEGIN',
    'ORCHESTRATOR_END',
    'MODEL_LOAD',
    'FORENSIC_BYPASS',
    'FORENSIC_CHAT_SEND',
    'FORENSIC_CONVERSATION_START',
    'FORENSIC_INFERENCE_SERVICE_ENTRY',
    'FORENSIC_PROVIDER_ENTRY',
    'FORENSIC_STREAM_ENTRY',
  };

  static const Set<String> _fallbackTags = {
    'FALLBACK',
    'RUNTIME_PATH',
    'AI_RUNTIME_MONITOR',
  };

  static const Set<String> _tokenTags = {
    'TOKEN_STREAM',
    'TOKEN_LOOP',
    'TOKEN_EMIT',
    'DART_TOKEN_RECEIVED',
    'DART_STREAM_RECEIVE',
    'DART_STREAM_RENDER',
    'FFI_CALLBACK_ENTER',
    'FFI_CALLBACK_PAYLOAD',
  };

  static const Set<String> _streamTags = {
    'STREAM_ADD',
    'STREAM_FLUSH',
    'STREAM_CLOSE',
    'FINAL_RESPONSE',
    'DART_STREAM_LISTEN',
    'DART_STREAM_CLOSE',
  };

  static const Set<String> _validationTags = {
    'VALIDATION',
    'MODEL_PATH',
    'MODEL_EXISTS',
    'MODEL_SIZE',
    'MODEL_READABLE',
  };
}

/// Mixin that wires a class's private `_log` calls to [RuntimeEventLog].
///
/// Classes that mix this in can call [logEvent] to emit to both
/// [debugPrint] and the shared [RuntimeEventLog].
mixin RuntimeEventEmitter {
  void logEvent(String tag, String message) {
    final full = '[$tag] $message';
    debugPrint(full);
    RuntimeEventLog.instance.emit(full);
  }
}
