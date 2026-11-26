import 'dart:convert';
import 'diagnostics.dart';

/// Reports contain only typed events, rounded to UTC minute; no installation
/// ID, device name, raw error, stack, prompt or application-domain data.
class DiagnosticReport {
  DiagnosticReport._(this.events);
  final List<Map<String, Object>> events;
  static const maxEvents = 100;

  static DiagnosticReport fromSafeHistory(String history) {
    final events = <Map<String, Object>>[];
    final pattern = RegExp(r'^\[(\d{4}-\d\d-\d\dT[\d:.+Z-]+)\] \[AIVEXUS_DIAGNOSTIC\] \[AIVEXUS_DIAGNOSTIC\] component=([a-z]+) event=([a-z]+)(?: elapsed_ms=(\d{1,8}))?$');
    for (final line in history.split('\n').reversed) {
      final match = pattern.firstMatch(line);
      if (match == null || match.end != line.length) continue;
      final date = DateTime.tryParse(match[1]!);
      if (date == null) continue;
      final utc = date.toUtc();
      final time = DateTime.utc(utc.year, utc.month, utc.day, utc.hour, utc.minute);
      final event = <String, Object>{
        'time': time.toIso8601String(), 'component': match[2]!, 'event': match[3]!,
        if (match[4] != null) 'elapsed_ms': int.parse(match[4]!),
      };
      if (!_valid(event)) continue;
      events.add(Map.unmodifiable(event));
      if (events.length == maxEvents) break;
    }
    return DiagnosticReport._(List.unmodifiable(events.reversed));
  }

  static bool _valid(Map event) {
    if (event.keys.any((key) => !const {'time','component','event','elapsed_ms'}.contains(key))) return false;
    final time = event['time'];
    if (time is! String || !RegExp(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:00\.000Z$').hasMatch(time)) return false;
    final parsed = DateTime.tryParse(time);
    if (parsed == null || parsed.toIso8601String() != time) return false;
    if (!DiagnosticComponent.values.any((c) => c.name == event['component']) ||
        !DiagnosticEvent.values.any((e) => e.name == event['event'])) return false;
    final duration = event['elapsed_ms'];
    return !event.containsKey('elapsed_ms') || duration is int && duration >= 0 && duration <= 86400000;
  }

  String get json => jsonEncode({'schema': 1, 'events': events});

  /// Validate persisted input again before any network operation.
  static DiagnosticReport decode(String input) {
    if (input.length > 32768) throw const FormatException('Report too large');
    final decoded = jsonDecode(input);
    if (decoded is! Map || decoded.length != 2 || decoded['schema'] != 1 ||
        decoded['events'] is! List) throw const FormatException('Invalid report');
    final list = decoded['events'] as List;
    if (list.length > maxEvents || list.isEmpty) throw const FormatException('Invalid event count');
    final events = <Map<String, Object>>[];
    for (final item in list) {
      if (item is! Map || !_valid(item)) throw const FormatException('Invalid event');
      events.add(Map.unmodifiable(Map<String, Object>.from(item)));
    }
    return DiagnosticReport._(List.unmodifiable(events));
  }
}
