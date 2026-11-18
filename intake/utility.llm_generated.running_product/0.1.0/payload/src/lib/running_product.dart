class RunningProductCalculator {
  static List<int> runningProducts(List<int> input) {
    List<int> result = [];
    int product = 1;

    for (int i = 0; i < input.length; i++) {
      if (input[i] == 0) {
        product = 0;
      } else {
        product *= input[i];
      }
      result.add(product);
    }

    return result;
  }
}

void main() {
  // Test cases
  print(RunningProductCalculator.runningProducts([])); // Output: [0]
  print(
      RunningProductCalculator.runningProducts([1, 2, 3])); // Output: [1, 2, 6]
  print(
      RunningProductCalculator.runningProducts([0, 2, 3])); // Output: [0, 0, 0]
  print(RunningProductCalculator.runningProducts(
      [-1, 2, 3])); // Output: [-1, -2, -6]
  print(
      RunningProductCalculator.runningProducts([1, 0, 3])); // Output: [1, 0, 0]
}

List<int> runningProducts(List<int> input) =>
    RunningProductCalculator.runningProducts(input);
