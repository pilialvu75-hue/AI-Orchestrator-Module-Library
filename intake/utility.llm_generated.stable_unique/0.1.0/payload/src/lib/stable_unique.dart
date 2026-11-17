class StableUnique {
  static List<int> uniqueStable(List<int> input) {
    final Set<int> seen = <int>{};
    final List<int> result = <int>[];

    for (final int num in input) {
      if (!seen.contains(num)) {
        seen.add(num);
        result.add(num);
      }
    }

    return result;
  }
}

List<int> uniqueStable(List<int> input) => StableUnique.uniqueStable(input);
