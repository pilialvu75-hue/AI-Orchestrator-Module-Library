import 'dart:math' show max;

class MaxRunLength {
  static int longestRunLength(List<int> input) {
    if (input.isEmpty) return 0;
    if (input.length == 1) return 1;

    int maxLength = 1;
    int currentLength = 1;

    for (int i = 1; i < input.length; i++) {
      if (input[i] == input[i - 1]) {
        currentLength++;
      } else {
        maxLength = max(maxLength, currentLength);
        currentLength = 1;
      }
    }

    maxLength = max(maxLength, currentLength);
    return maxLength;
  }
}

int longestRunLength(List<int> input) => MaxRunLength.longestRunLength(input);
