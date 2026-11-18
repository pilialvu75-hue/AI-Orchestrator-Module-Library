class RotateLeft {
  static List<int> rotateLeft(List<int> input, int steps) {
    if (input.isEmpty) return [];

    int length = input.length;
    steps = steps % length; // Handle cases where steps > length
    if (steps == 0) return input; // No rotation needed

    List<int> rotated = List<int>.from(input);
    List<int> rotatedLeft = List<int>.from(rotated.sublist(steps));
    List<int> rotatedRight = List<int>.from(rotated.sublist(0, steps));

    rotatedLeft.addAll(rotatedRight);

    return rotatedLeft;
  }
}

List<int> rotateLeft(List<int> input, int steps) =>
    RotateLeft.rotateLeft(input, steps);
