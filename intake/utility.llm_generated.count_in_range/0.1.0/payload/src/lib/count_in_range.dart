class AivexusCountInRange {
  static int countInRange(List<int> input, int lower, int upper) {
    if (lower > upper) {
      return 0;
    }
    int count = 0;
    for (int x in input) {
      if (x >= lower && x <= upper) {
        count++;
      }
    }
    return count;
  }
}

int countInRange(List<int> input, int lower, int upper) =>
    AivexusCountInRange.countInRange(input, lower, upper);
