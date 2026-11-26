import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Disk-backed persistence for [RuntimeEventLog] entries.
///
/// [RuntimeEventLog] on its own only keeps entries in memory.
/// If the app process is killed by a native crash — for example
/// a SIGSEGV inside a native runtime — the in-memory buffer dies
/// with the process.
///
/// This sink appends every log line to a plain text file on disk,
/// synchronously and with an immediate flush, so the events written
/// immediately before a native crash remain available on the next
/// application launch.
///
/// This is diagnostic infrastructure only: every method deliberately
/// fails safe. A logging problem must never crash the application.
class RuntimeCrashLogSink {
  RuntimeCrashLogSink._();

  /// Singleton instance shared across the app.
  static final RuntimeCrashLogSink instance =
      RuntimeCrashLogSink._();

  static const String _fileName =
      'runtime_crash_log.txt';

  /// Safety cap for the persistent forensic log.
  ///
  /// 1 MB is intentionally enough for many hundreds/thousands of
  /// diagnostic events while remaining practical to inspect on a
  /// mobile device.
  ///
  /// When this threshold is exceeded, the oldest half of the log is
  /// discarded and the most recent half is kept.
  static const int _maxFileBytes =
      1 * 1024 * 1024;

  File? _file;

  bool _ready = false;

  bool _initFailed = false;

  /// Prepares the on-disk log file.
  ///
  /// This should be awaited once, as early as possible in main(),
  /// before runtime/inference/voice activity starts.
  Future<void> init() async {
    try {
      final directory =
          await getApplicationDocumentsDirectory();

      final file = File(
        '${directory.path}/$_fileName',
      );

      if (!file.existsSync()) {
        file.createSync(
          recursive: true,
        );
      }

      _file = file;

      _ready = true;

      _initFailed = false;

      // An installation upgraded from an older build may already
      // contain the previous multi-megabyte diagnostic file.
      // Apply the new limit immediately instead of waiting for the
      // next append.
      _enforceMaxSizeIfNeeded(
        file,
      );
    } catch (_) {
      _initFailed = true;

      _ready = false;
    }
  }

  /// Appends [line] synchronously and flushes it immediately.
  ///
  /// Persistence happens before dangerous native calls so the last
  /// forensic marker has the best possible chance of surviving a
  /// process-level crash.
  void append(
    String line,
  ) {
    final file = _file;

    if (!_ready ||
        file == null) {
      return;
    }

    try {
      file.writeAsStringSync(
        '$line\n',
        mode:
            FileMode.append,
        flush: true,
      );

      _enforceMaxSizeIfNeeded(
        file,
      );
    } catch (_) {
      // Diagnostic persistence is best-effort.
      // Never let a logging error terminate the application.
    }
  }

  void _enforceMaxSizeIfNeeded(
    File file,
  ) {
    try {
      final length =
          file.lengthSync();

      if (length <=
          _maxFileBytes) {
        return;
      }

      final content =
          file.readAsStringSync();

      if (content.isEmpty) {
        return;
      }

      final approximateKeepFrom =
          content.length ~/ 2;

      // Prefer starting from a complete log line instead of cutting
      // through the middle of an event.
      final nextLineBreak =
          content.indexOf(
        '\n',
        approximateKeepFrom,
      );

      final keepFrom =
          nextLineBreak >= 0
              ? nextLineBreak + 1
              : approximateKeepFrom;

      final trimmed =
          content.substring(
        keepFrom,
      );

      file.writeAsStringSync(
        '[LOG_TRUNCATED_TO_LIMIT_BYTES='
        '$_maxFileBytes]\n'
        '$trimmed',
        mode:
            FileMode.write,
        flush: true,
      );
    } catch (_) {
      // Best-effort housekeeping only.
    }
  }

  /// Reads the full persisted log as text.
  ///
  /// Returns a human-readable placeholder rather than throwing when
  /// persistence is unavailable because this text is shown directly
  /// by Debug Lab.
  Future<String> readAsText() async {
    final file = _file;

    if (!_ready ||
        file == null) {
      if (_initFailed) {
        return '(log su disco non disponibile: '
            'inizializzazione fallita)';
      }

      return '(log su disco non ancora inizializzato)';
    }

    try {
      if (!await file.exists()) {
        return '(nessun log salvato finora)';
      }

      final content =
          await file.readAsString();

      return content.trim().isEmpty
          ? '(file di log presente ma vuoto)'
          : content;
    } catch (error) {
      return '(errore durante la lettura del log: '
          '$error)';
    }
  }

  /// Clears the persistent forensic log.
  ///
  /// The file itself is intentionally retained so persistence can
  /// immediately resume without having to recreate the sink.
  Future<void> clear() async {
    final file = _file;

    if (file == null) {
      return;
    }

    try {
      if (await file.exists()) {
        await file.writeAsString(
          '',
          mode:
              FileMode.write,
          flush: true,
        );
      }
    } catch (_) {
      // Clearing diagnostics must never crash the app.
    }
  }

  /// Absolute path of the persisted log file.
  ///
  /// Intended only for diagnostics/display purposes.
  String? get filePath =>
      _file?.path;
}
