import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

void main() {
  test('closed vocabulary discards raw abort text and invalid timestamps', () async {
    final ts = DateTime.now().subtract(const Duration(seconds: 5)).millisecondsSinceEpoch;
    final monitor = DiagnosticExitHistory(reader: () async => [
      {'timestamp_ms': ts, 'reason': 'native_crash', 'abort_message': 'private data'},
      {'timestamp_ms': ts, 'reason': 'native_crash', 'description': 'another private string'},
      {'timestamp_ms': -1, 'reason': 'managed_crash'},
    ]);
    addTearDown(monitor.dispose);
    await monitor.refresh();
    expect(monitor.status, ExitHistoryStatus.available);
    expect(monitor.records, hasLength(1));
    expect(monitor.records.single.reason, ExitReason.nativeCrash);
    expect(monitor.records.single.timestamp.millisecondsSinceEpoch, ts);
  });
  testWidgets('late historical response survives startup timeout', (tester) async {
    final response = Completer<List<dynamic>?>();
    final monitor = DiagnosticExitHistory(reader: () => response.future);
    addTearDown(monitor.dispose);
    final result = monitor.refresh();
    await tester.pump(const Duration(seconds: 3));
    await result;
    expect(monitor.status, ExitHistoryStatus.loading);
    response.complete([{'timestamp_ms': 1234, 'reason': 'user_requested'}]);
    await tester.pump();
    expect(monitor.status, ExitHistoryStatus.available);
    expect(monitor.records.single.reason, ExitReason.userRequested);
  });
  test('unsupported history is not a clean-exit report', () async {
    final monitor = DiagnosticExitHistory(reader: () async => null);
    addTearDown(monitor.dispose);
    await monitor.refresh();
    expect(monitor.status, ExitHistoryStatus.unavailable);
  });
}
