class CumulativeMaxCalculator {
  static List<int> cumulativeMaximum(List<int> input) {
    if (input.isEmpty) return [];

    List<int> result = List.filled(input.length, 0);
    int currentMax = input[0];

    for (int i = 0; i < input.length; i++) {
      currentMax = input[i] > currentMax ? input[i] : currentMax;
      result[i] = currentMax;
    }

    return result;
  }
}

void main() {
  // Test cases
  print(CumulativeMaxCalculator.cumulativeMaximum([])); // Output: []
  print(CumulativeMaxCalculator.cumulativeMaximum(
      [-1, 3, -2, 5, 0])); // Output: [-1, 3, 3, 5, 5]
  print(CumulativeMaxCalculator.cumulativeMaximum(
      [1, 2, 3, 4, 5])); // Output: [1, 2, 3, 4, 5]
  print(CumulativeMaxCalculator.cumulativeMaximum(
      [5, 4, 3, 2, 1])); // Output: [5, 5, 5, 5, 5]
  print(CumulativeMaxCalculator.cumulativeMaximum(
      [-5, -4, -3, -2, -1])); // Output: [-5, -4, -3, -2, -1]
  print(CumulativeMaxCalculator.cumulativeMaximum(
      [0, 0, 0, 0, 0])); // Output: [0, 0, 0, 0, 0]
  print(CumulativeMaxCalculator.cumulativeMaximum(
      [1, -1, 1, -1, 1])); // Output: [1, 1, 1, 1, 1]
}

List<int> cumulativeMaximum(List<int> input) =>
    CumulativeMaxCalculator.cumulativeMaximum(input);
