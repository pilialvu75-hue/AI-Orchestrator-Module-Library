class FixedChunks {
  static List<List<int>> chunkIntegers(List<int> input, int chunkSize) {
    if (chunkSize <= 0) {
      throw ArgumentError('chunkSize must be greater than zero');
    }
    if (input.isEmpty) {
      return [];
    }

    List<List<int>> chunks = [];
    int startIndex = 0;

    while (startIndex < input.length) {
      int endIndex = startIndex + chunkSize;
      if (endIndex > input.length) {
        endIndex = input.length;
      }

      chunks.add(input.sublist(startIndex, endIndex));
      startIndex = endIndex;
    }

    return chunks;
  }
}

List<List<int>> chunkIntegers(List<int> input, int chunkSize) =>
    FixedChunks.chunkIntegers(input, chunkSize);
