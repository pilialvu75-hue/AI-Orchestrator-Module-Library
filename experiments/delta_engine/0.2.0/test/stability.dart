import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import '../lib/delta_engine.dart';

void check(bool ok, String label) {
  if (!ok) throw StateError(label);
}
void equal(List<int> a, List<int> b) {
  check(a.length == b.length, 'length mismatch');
  for (var i = 0; i < a.length; i++) {
    check(a[i] == b[i], 'sample mismatch at $i');
  }
}
void roundTrip(List<int> data) {
  final before = List<int>.of(data);
  equal(DeltaEngine.decode(DeltaEngine.encode(data)), before);
  equal(data, before);
}
void reject(List<int> bytes, {int limit = 10000000}) {
  try {
    DeltaEngine.decode(Uint8List.fromList(bytes), maxSamples: limit);
  } on FormatException {
    return;
  }
  throw StateError('malformed frame accepted');
}
void benchmark(String name, List<int> data) {
  final raw = ByteData(data.length * 8);
  for (var i = 0; i < data.length; i++) {
    raw.setInt64(i * 8, data[i], Endian.little);
  }
  final timer = Stopwatch()..start();
  final encoded = DeltaEngine.encode(data);
  final encodeUs = timer.elapsedMicroseconds;
  timer.reset();
  final decoded = DeltaEngine.decode(encoded);
  final decodeUs = timer.elapsedMicroseconds;
  equal(decoded, data);
  final gz = gzip.encode(raw.buffer.asUint8List());
  final deltaGz = gzip.encode(encoded);
  print('$name raw=${raw.lengthInBytes} delta=${encoded.length} gzip=${gz.length} delta_gzip=${deltaGz.length} encode_us=$encodeUs decode_us=$decodeUs');
}
void main() {
  const magic = [68, 67, 69, 50];
  equal(DeltaEngine.encode([0, 1, 0, -1]), [...magic, 4, 0, 2, 1, 1]);
  for (final data in <List<int>>[
    [], [0], [-1], [1,1,1],
    [9223372036854775807, -9223372036854775807 - 1, 0],
    [-9223372036854775807 - 1, 9223372036854775807],
  ]) {
    roundTrip(data);
  }
  final r = Random(42);
  for (var i = 0; i < 1000; i++) {
    roundTrip(List.generate(r.nextInt(256), (_) => r.nextInt(2000000000) - 1000000000));
  }
  reject([]);
  reject([...magic, 1]);
  reject([...magic, 0, 0]);
  reject([...magic, 1, 128, 0]);
  reject([...magic, 1, ...List.filled(9, 255), 2]);
  reject([...magic, 2, 0, 0], limit: 1);
  final frame = DeltaEngine.encode([4200, 4202, 4205, 4204, 4208, 4209]);
  for (var i = 0; i < frame.length; i++) {
    reject(frame.sublist(0, i));
  }
  check(frame.length == 12, 'unexpected framed length');
  benchmark('smooth_telemetry', List.generate(100000, (i) => 4200 + i % 10));
  benchmark('constant', List.filled(100000, 42));
  benchmark('noisy', List.generate(100000, (_) => r.nextInt(2000000000) - 1000000000));
  benchmark('large', List.generate(1000000, (i) => i));
  print('PASS: binary codec edge cases, random round trips and malformed framing');
}
