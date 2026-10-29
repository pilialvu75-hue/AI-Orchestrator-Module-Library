import 'package:aivexus_external_logging/aivexus_external_logging.dart';
import 'package:logging/logging.dart';

void check(bool ok, String reason) {
  if (!ok) throw StateError('FAIL: $reason');
}

Future<void> main() async {
  final globals = <LogRecord>[];
  final globalSub = Logger.root.onRecord.listen(globals.add);
  final module = AivexusLoggingModule(capacity: 2);
  module.emit('startup_ready', severity: AivexusSeverity.info);
  module.emit('local_model_loaded', severity: AivexusSeverity.debug);
  module.emit('retry_scheduled', severity: AivexusSeverity.warning);

  final events = module.snapshot();
  check(events.length == 2, 'bounded local ring buffer');
  check(events.first.eventCode == 'local_model_loaded', 'FIFO eviction');
  check(events.first.severity == AivexusSeverity.debug, 'debug maps through upstream Logger');
  check(events.last.eventCode == 'retry_scheduled', 'latest event');
  check(events.last.severity == AivexusSeverity.warning, 'warning maps through upstream Logger');
  check(events.last.toJson()['severity'] == 'warning', 'structured output');
  check(events.last.timestampUtc.isUtc, 'UTC event timestamps');
  check(globals.isEmpty, 'no global logger capture');

  for (final unsafe in ['my password=secret', '../tmp/secret', '', 'x' * 65]) {
    var refused = false;
    try {
      module.emit(unsafe);
    } on ArgumentError {
      refused = true;
    }
    check(refused, 'unsafe event rejected');
  }
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
    module.emit('after_dispose');
  } on StateError {
    closed = true;
  }
  check(closed, 'closed module rejects new events');
  await globalSub.cancel();
  print('PASS: external dart-lang/logging + real Aivexus adapter (local, isolated, offline)');
}
