import 'package:aivexus_external_logging_flutter_demo/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Flutter host displays real external Dart log events', (tester) async {
    await tester.pumpWidget(const ExternalLoggingDemoApp());
    expect(find.text('PROVA LOCALE — NON CERTIFICATO'), findsOneWidget);
    expect(find.text('Eventi locali: 0'), findsOneWidget);

    await tester.tap(find.byKey(const Key('emit-start')));
    await tester.pump();
    expect(find.text('Eventi locali: 1'), findsOneWidget);
    expect(find.text('startup_ready'), findsOneWidget);

    await tester.tap(find.byKey(const Key('emit-model')));
    await tester.pump();
    expect(find.text('Eventi locali: 2'), findsOneWidget);
    expect(find.text('local_model_loaded'), findsOneWidget);

    await tester.tap(find.byKey(const Key('emit-retry')));
    await tester.pump();
    expect(find.text('Eventi locali: 3'), findsOneWidget);
    expect(find.text('retry_scheduled'), findsOneWidget);
    expect(find.text('Livello: warning'), findsOneWidget);
  });
}
