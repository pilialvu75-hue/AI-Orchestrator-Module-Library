class DeltaCodec {
  static List<int> encodeDeltas(List<int> samples) {
    if (samples.isEmpty) return [];
    List<int> encoded = [samples[0]];
    for (int i = 1; i < samples.length; i++) {
      encoded.add(samples[i] - samples[i - 1]);
    }
    return encoded;
  }

  static List<int> decodeDeltas(List<int> deltas) {
    if (deltas.isEmpty) return [];
    List<int> decoded = [deltas[0]];
    for (int i = 1; i < deltas.length; i++) {
      decoded.add(decoded[i - 1] + deltas[i]);
    }
    return decoded;
  }
}

List<int> encodeDeltas(List<int> samples) => DeltaCodec.encodeDeltas(samples);
List<int> decodeDeltas(List<int> deltas) => DeltaCodec.decodeDeltas(deltas);
