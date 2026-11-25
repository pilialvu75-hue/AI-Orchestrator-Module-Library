import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:__PROJECT_SLUG__/main.dart';

void main() {
  for (final entry in AppHome.labels.entries) {
    testWidgets('renders clean shell in ${entry.key}', (tester) async {
      await tester.pumpWidget(AivexusApp(locale: Locale(entry.key)));
      await tester.pumpAndSettle();
      expect(find.text(appName), findsOneWidget);
      expect(find.text(entry.value), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
