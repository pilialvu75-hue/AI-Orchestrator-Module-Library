class InterleaveLists {
  static List<int> interleaveIntegers(List<int> left, List<int> right) {
    final List<int> result = [];
    final int minLength =
        left.length < right.length ? left.length : right.length;

    for (int i = 0; i < minLength; i++) {
      result.add(left[i]);
      result.add(right[i]);
    }

    if (left.length > minLength) {
      result.addAll(left.sublist(minLength));
    } else if (right.length > minLength) {
      result.addAll(right.sublist(minLength));
    }

    return result;
  }
}

List<int> interleaveIntegers(List<int> left, List<int> right) =>
    InterleaveLists.interleaveIntegers(left, right);
