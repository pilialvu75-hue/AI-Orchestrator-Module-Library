import 'package:aivexus_external_logging/aivexus_external_logging.dart';
import 'package:logging/logging.dart';

void check(bool ok, String reason) {
  if (!ok) throw StateError('FAIL: $reason');
}

Future<void> main() async {
  final globals = <LogRecord>[];
  final globalSub = Logger.root.onRecord.listen(globals.add);
  final module = AivexusLoggingModule(capacity: 2);
  module.emit(AivexusEventCode.startupReady, severity: AivexusSeverity.info);
  module.emit(AivexusEventCode.localModelLoaded, severity: AivexusSeverity.debug);
  module.emit(AivexusEventCode.retryScheduled, severity: AivexusSeverity.warning);

  final events = module.snapshot();
  check(events.length == 2, 'bounded local ring buffer');
  check(events.first.eventCode == 'local_model_loaded', 'FIFO eviction');
  check(events.first.severity == AivexusSeverity.debug, 'debug maps through upstream Logger');
  check(events.last.eventCode == 'retry_scheduled', 'latest event');
  check(events.last.severity == AivexusSeverity.warning, 'warning maps through upstream Logger');
  check(events.last.toJson()['severity'] == 'warning', 'structured output');
  check(events.last.timestampUtc.isUtc, 'UTC event timestamps');
  check(globals.isEmpty, 'no global logger capture');

  // Even a syntactically acceptable identifier cannot be an event:
  // dynamic dispatch still enforces the enum type at runtime.
  for (final unsafe in ['password_123', 'user_email_abc', '../tmp/path', '']) {
    var refused = false;
    try {
      final dynamic dynamicEmit = module.emit;
      dynamicEmit(unsafe);
    } on TypeError {
      refused = true;
    }
    check(refused, 'unapproved free text rejected at runtime');
  }
  check(module.snapshot().length == 2, 'invalid input leaves no new event');
  var invalidCapacity = false;
  try {
    AivexusLoggingModule(capacity: 0);
  } on RangeError {
    invalidCapacity = true;
  }
  check(invalidCapacity, 'invalid capacity rejected');

  final snapshot = module.snapshot();
  var immutable = false;
  try {
    snapshot.clear();
  } on UnsupportedError {
    immutable = true;
  }
  check(immutable, 'returned snapshot immutable');
  await module.dispose();
  await module.dispose();
  check(module.snapshot().isEmpty, 'disposed buffer cleared');
  var closed = false;
  try {
    module.emit(AivexusEventCode.consumerStarted);
  } on StateError {
    closed = true;
  }
  check(closed, 'closed module rejects new events');
  await globalSub.cancel();
  print('PASS: typed closed-vocabulary external Dart logging adapter (offline)');
}
