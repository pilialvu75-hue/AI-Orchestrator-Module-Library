import 'package:aivexus_external_async/aivexus_external.dart' as aivexus;

Future<void> main() async {
  final queue = aivexus.StreamQueue<int>(Stream<int>.fromIterable([2, 4, 6]));
  if (await queue.next != 2) throw StateError('first');
  if (await queue.peek != 4) throw StateError('peek');
  if (await queue.next != 4) throw StateError('second');
  if (await queue.next != 6) throw StateError('third');
  if (await queue.hasNext) throw StateError('exhaustion');
  await queue.cancel();
  print('PASS: independently executed packaged AIVEXUS async adapter');
}
