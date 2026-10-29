import 'package:aivexus_external_logging/aivexus_external_logging.dart';

Future<void> main() async {
  final module = AivexusLoggingModule(capacity: 2);
  try {
    module.emit(AivexusEventCode.consumerStarted);
    module.emit(AivexusEventCode.moduleConnected,
        severity: AivexusSeverity.warning);
    final events = module.snapshot();
    if (events.length != 2 ||
        events[0].eventCode != 'consumer_started' ||
        events[1].eventCode != 'module_connected' ||
        events[1].severity != AivexusSeverity.warning ||
        events[1].toJson()['severity'] != 'warning') {
      throw StateError('Aivexus typed external logging contract failed');
    }
    var rejected = false;
    try {
      final dynamic dispatch = module.emit;
      dispatch('customer_id_123');
    } on TypeError {
      rejected = true;
    }
    if (!rejected || module.snapshot().length != 2) {
      throw StateError('Unreviewed free text reached typed external log');
    }
    print('PASS: independent app consumes typed public Dart logging module');
  } finally {
    await module.dispose();
  }
}
