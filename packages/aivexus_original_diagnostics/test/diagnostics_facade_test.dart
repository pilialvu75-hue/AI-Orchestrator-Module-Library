import 'dart:io';
import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_event_log.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

class TestPaths extends PathProviderPlatform {
  TestPaths(this.directory);
  final String directory;
  @override
  Future<String?> getApplicationDocumentsPath() async => directory;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('closed vocabulary persists local events and recovers previous history', () async {
    final directory = await Directory.systemTemp.createTemp('aivexus-diagnostics-');
    final previous = PathProviderPlatform.instance;
    final diagnostics = AivexusDiagnostics.instance;
    PathProviderPlatform.instance = TestPaths(directory.path);
    try {
      await diagnostics.initialize();
      await diagnostics.clear();
      diagnostics.record(DiagnosticComponent.updater, DiagnosticEvent.failed, elapsedMs: 150);
      RuntimeEventLog.instance.emit('[SECRET] private-user-text');
      RuntimeEventLog.instance.emit('[AIVEXUS_DIAGNOSTIC] component=application event=failed path=private-user-text');
      final stored = await diagnostics.readLocalHistory();
      expect(stored, isNot(contains('private-user-text')));
      expect(diagnostics.entries, hasLength(1));
      expect(stored, contains('component=updater event=failed elapsed_ms=150'));
      await diagnostics.initialize();
      expect(await diagnostics.readLocalHistory(), contains('component=updater event=failed'));
      diagnostics.record(DiagnosticComponent.application, DiagnosticEvent.started, elapsedMs: -1);
      expect(diagnostics.entries.last.message, isNot(contains('elapsed_ms')));
      await diagnostics.clear();
      expect(await diagnostics.readLocalHistory(), isNot(contains('component=updater')));
    } finally {
      PathProviderPlatform.instance = previous;
      await directory.delete(recursive: true);
    }
  });
}
