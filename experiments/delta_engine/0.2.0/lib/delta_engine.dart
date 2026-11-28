import 'dart:typed_data';

/// Lossless signed 64-bit delta + ZigZag + unsigned LEB128.
/// Deltas use modular 64-bit arithmetic; BigInt avoids platform overflow.
/// Format: DCE2 magic, sample count, canonical varints. No checksum in v0.2.
class DeltaEngine {
  static const version = '0.2.0';
  static final _mod = BigInt.one << 64;
  static final _half = BigInt.one << 63;
  static final _mask = _mod - BigInt.one;
  static final _seven = BigInt.from(127);
  static BigInt _signed(BigInt x) {
    final y = x & _mask;
    return y >= _half ? y - _mod : y;
  }
  static void _write(BytesBuilder out, BigInt n) {
    while (n >= BigInt.from(128)) {
      out.addByte((n & _seven).toInt() | 128);
      n >>= 7;
    }
    out.addByte(n.toInt());
  }
  static Uint8List encode(List<int> samples) {
    final out = BytesBuilder(copy: false)..add([68, 67, 69, 50]);
    _write(out, BigInt.from(samples.length));
    var previous = BigInt.zero;
    for (final sample in samples) {
      final current = BigInt.from(sample);
      final delta = _signed(current - previous);
      final z = delta >= BigInt.zero ? delta << 1 : ((-delta) << 1) - BigInt.one;
      _write(out, z);
      previous = current;
    }
    return out.takeBytes();
  }
  static List<int> decode(Uint8List bytes, {int maxSamples = 10000000}) {
    if (maxSamples < 0) throw ArgumentError.value(maxSamples);
    if (bytes.length < 5 || bytes[0] != 68 || bytes[1] != 67 ||
        bytes[2] != 69 || bytes[3] != 50) throw FormatException('Invalid DCE2 header');
    var pos = 4;
    BigInt read() {
      var value = BigInt.zero;
      for (var i = 0; i < 10; i++) {
        if (pos >= bytes.length) throw FormatException('Truncated varint');
        final b = bytes[pos++];
        if (i == 9 && b > 1) throw FormatException('Varint overflow');
        value |= BigInt.from(b & 127) << (7 * i);
        if (b < 128) {
          if (i > 0 && b == 0) throw FormatException('Noncanonical varint');
          return value;
        }
      }
      throw FormatException('Varint overflow');
    }
    final count = read();
    if (count > BigInt.from(maxSamples) || count > BigInt.from(bytes.length - pos)) {
      throw FormatException('Sample count exceeds limit or input');
    }
    final result = <int>[];
    var previous = BigInt.zero;
    for (var i = 0; i < count.toInt(); i++) {
      final z = read();
      final delta = z.isEven ? z >> 1 : -((z >> 1) + BigInt.one);
      previous = _signed(previous + delta);
      result.add(previous.toInt());
    }
    if (pos != bytes.length) throw FormatException('Trailing bytes');
    return result;
  }
}
