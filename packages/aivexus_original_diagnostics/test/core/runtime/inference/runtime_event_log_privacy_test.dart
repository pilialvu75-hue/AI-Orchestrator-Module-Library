import 'package:flutter_test/flutter_test.dart';

import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_event_log.dart';

void main() {
  group('RuntimeEventLog central privacy boundary', () {
    test('redacts a legacy quoted Web query before diagnostics retain it', () {
      const sensitive =
          '[TOOL_INTERCEPTOR] target=search status=extracted '
          'query="best player with \"private phrase\"\nand another line"';

      final safe = RuntimeEventLog.redactSensitiveFields(sensitive);

      expect(
        safe,
        '[TOOL_INTERCEPTOR] target=search status=extracted '
        'query="[REDACTED]"',
      );
      expect(safe, isNot(contains('private phrase')));
      expect(safe, isNot(contains('another line')));
    });

    test('keeps length-only query diagnostics unchanged', () {
      const safe = '[WEBSEARCH_ENTER] query_chars=42 limit=5';

      expect(RuntimeEventLog.redactSensitiveFields(safe), safe);
    });

    test('emit stores only the redacted query in the shared runtime log', () {
      final log = RuntimeEventLog.instance;
      log.clear();
      addTearDown(log.clear);

      log.emit(
        '[TOOL_EXECUTION_BEGIN] tool=web_search session=test '
        'query="medical appointment near my home"',
      );

      expect(log.entries, hasLength(1));
      final entry = log.entries.single;
      expect(entry.tag, 'TOOL_EXECUTION_BEGIN');
      expect(entry.message, contains('query="[REDACTED]"'));
      expect(entry.message, isNot(contains('medical appointment')));
      expect(entry.message, isNot(contains('near my home')));
    });
  });
}
