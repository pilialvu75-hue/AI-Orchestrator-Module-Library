class AivexusIndexPositions {
  static Map<int, List<int>> groupIndices(List<int> input) {
    final Map<int, List<int>> result = <int, List<int>>{};
    for (int i = 0; i < input.length; i++) {
      final int value = input[i];
      if (!result.containsKey(value)) {
        result[value] = <int>[];
      }
      result[value]!.add(i);
    }
    return result;
  }
}

void main() {
  // Test cases
  final List<int> test1 = [1, 2, 3, 2, 1, 4, 2];
  final List<int> test2 = [5, 5, 5, 5, 5];
  final List<int> test3 = [];

  print(AivexusIndexPositions.groupIndices(
      test1)); // {1: [0, 4, 5], 2: [1, 3, 7], 3: [2], 4: [6]}
  print(AivexusIndexPositions.groupIndices(test2)); // {5: [0, 1, 2, 3, 4]}
  print(AivexusIndexPositions.groupIndices(test3)); // {}
}

Map<int, List<int>> groupIndices(List<int> input) =>
    AivexusIndexPositions.groupIndices(input);
