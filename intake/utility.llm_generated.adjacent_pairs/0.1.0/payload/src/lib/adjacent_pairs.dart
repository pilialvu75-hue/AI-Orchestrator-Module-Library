class AivexusAdjacentPairs {
  static List<List<int>> adjacentPairs(List<int> input) {
    if (input.length < 2) {
      return [];
    }

    List<List<int>> result = [];
    for (int i = 0; i < input.length - 1; i++) {
      result.add([input[i], input[i + 1]]);
    }

    return result;
  }
}

List<List<int>> adjacentPairs(List<int> input) =>
    AivexusAdjacentPairs.adjacentPairs(input);
