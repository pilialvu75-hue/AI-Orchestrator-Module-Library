import 'package:aivexus_external_logging/aivexus_external_logging.dart';

/// Real downstream use of a pinned tested Library candidate.
/// This does NOT install the package into the AI-Orchestrator app.
Future<void> main() async {
  final module = AivexusLoggingModule(capacity: 3);
  try {
    module.emit('consumer_started', severity: AivexusSeverity.info);
    module.emit('module_connected', severity: AivexusSeverity.warning);
    final events = module.snapshot();
    if (events.length != 2 ||
        events[0].eventCode != 'consumer_started' ||
        events[1].eventCode != 'module_connected' ||
        events[1].severity != AivexusSeverity.warning ||
        events[1].toJson()['severity'] != 'warning') {
      throw StateError('External Aivexus module contract failed in downstream app');
    }
    module.emit('third_event', severity: AivexusSeverity.info);
    module.emit('fourth_event', severity: AivexusSeverity.warning);
    final bounded = module.snapshot();
    if (bounded.length != 3 ||
        bounded[0].eventCode != 'module_connected' ||
        bounded[1].eventCode != 'third_event' ||
        bounded[2].eventCode != 'fourth_event') {
      throw StateError('External module bounded retention contract failed');
    }
    print('PASS: downstream real module events and bounded retention');
  } finally {
    await module.dispose();
  }
}
