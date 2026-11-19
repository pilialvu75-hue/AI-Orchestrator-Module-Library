class IntersectionUnique {
  static List<int> intersectStable(List<int> first, List<int> second) {
    final Set<int> setFirst = first.toSet();
    final Set<int> setSecond = second.toSet();
    final List<int> result = [];

    for (final int num in setFirst) {
      if (setSecond.contains(num)) {
        result.add(num);
      }
    }

    return result;
  }
}

void main() {
  // Test cases
  print(IntersectionUnique.intersectStable([], [])); // Output: []
  print(IntersectionUnique.intersectStable([1, 2, 3], [])); // Output: []
  print(IntersectionUnique.intersectStable([], [1, 2, 3])); // Output: []
  print(IntersectionUnique.intersectStable(
      [1, 2, 3], [1, 2, 3])); // Output: [1, 2, 3]
  print(IntersectionUnique.intersectStable([1, 2, 3], [4, 5, 6])); // Output: []
  print(IntersectionUnique.intersectStable(
      [1, 2, 3, 4], [3, 4, 5, 6])); // Output: [3, 4]
  print(IntersectionUnique.intersectStable(
      [1, 2, 3, 4], [1, 2, 3, 4])); // Output: [1, 2, 3, 4]
  print(IntersectionUnique.intersectStable(
      [1, 2, 3, 4], [1, 2, 3, 4, 5])); // Output: [1, 2, 3, 4]
  print(IntersectionUnique.intersectStable(
      [1, 2, 3, 4], [5, 6, 7, 8])); // Output: []
  print(IntersectionUnique.intersectStable(
      [1, 2, 3, 4, 5], [1, 2, 3, 4, 5])); // Output: [1, 2, 3, 4, 5]
  print(IntersectionUnique.intersectStable(
      [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6])); // Output: [1, 2, 3, 4, 5]
}

List<int> intersectStable(List<int> first, List<int> second) =>
    IntersectionUnique.intersectStable(first, second);
