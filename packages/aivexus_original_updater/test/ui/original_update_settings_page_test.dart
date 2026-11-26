import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:aivexus_original_updater/aivexus_original_updater.dart';
import 'package:aivexus_original_updater/ui/update_settings_page.dart';

class MockManager extends Mock implements UpdateManager {}

void main() {
  testWidgets('original settings page shows installed version and channel', (tester) async {
    final manager = MockManager();
    final state = ValueNotifier(UpdateState.initial(currentVersion: '1.2.3', preferredChannel: ReleaseChannel.stable));
    when(() => manager.state).thenReturn(state);
    when(() => manager.refreshDiagnostics()).thenAnswer((_) async {});
    when(() => manager.hasDetectedNewerVersion(state.value)).thenReturn(false);
    await tester.pumpWidget(MaterialApp(home: UpdateSettingsPage(updateManager: manager)));
    await tester.pumpAndSettle();
    expect(find.text('Updates'), findsOneWidget);
    expect(find.text('1.2.3'), findsOneWidget);
    expect(find.text('stable'), findsOneWidget);
    expect(find.text('Check now'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    state.dispose();
  });
}
