class IntegerFrequencies {
  static Map<int, int> countFrequencies(List<int> input) {
    Map<int, int> frequencyMap = <int, int>{};
    for (int number in input) {
      if (frequencyMap.containsKey(number)) {
        frequencyMap[number] = frequencyMap[number]! + 1;
      } else {
        frequencyMap[number] = 1;
      }
    }
    return frequencyMap;
  }
}

Map<int, int> countFrequencies(List<int> input) =>
    IntegerFrequencies.countFrequencies(input);
