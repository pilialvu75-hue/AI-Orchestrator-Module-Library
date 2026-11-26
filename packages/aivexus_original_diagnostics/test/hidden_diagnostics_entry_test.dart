import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

void main() {
  testWidgets('opens only on seventh tap and can reopen', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: HiddenDiagnosticsEntry(child: Text('1.0.0')))));
    for (var i = 0; i < 6; i++) {
      await tester.tap(find.text('1.0.0'));
      await tester.pump();
    }
    expect(find.text('Runtime Diagnostics'), findsNothing);
    await tester.tap(find.text('1.0.0'));
    await tester.pumpAndSettle();
    expect(find.text('Runtime Diagnostics'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    for (var i = 0; i < 7; i++) {
      await tester.tap(find.text('1.0.0'));
      await tester.pump();
    }
    await tester.pumpAndSettle();
    expect(find.text('Runtime Diagnostics'), findsOneWidget);
  });
  testWidgets('tap count expires and disabled entry does not open', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: HiddenDiagnosticsEntry(child: Text('1.0.0')))));
    for (var i = 0; i < 6; i++) {
      await tester.tap(find.text('1.0.0'));
      await tester.pump();
    }
    await tester.pump(const Duration(seconds: 6));
    await tester.tap(find.text('1.0.0'));
    await tester.pumpAndSettle();
    expect(find.text('Runtime Diagnostics'), findsNothing);
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: HiddenDiagnosticsEntry(enabled: false, child: Text('1.0.0')))));
    for (var i = 0; i < 7; i++) {
      await tester.tap(find.text('1.0.0'));
      await tester.pump();
    }
    expect(find.text('Runtime Diagnostics'), findsNothing);
  });
}
