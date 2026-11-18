class PalindromeFilter {
  static List<String> filterPalindromes(List<String> input) {
    List<String> palindromes = [];
    for (String str in input) {
      if (str == str.split('').reversed.join('')) {
        palindromes.add(str);
      }
    }
    return palindromes;
  }
}

void main() {
  List<String> testInput = [
    'radar',
    'hello',
    'world',
    '',
    'a',
    'ab',
    'aba',
    'racecar',
    'noon',
    'deified',
    'madam',
    'civic',
    'level',
    'rotor',
    'refer',
    'deified',
    'madam',
    'civic',
    'level',
    'rotor',
    'refer'
  ];
  List<String> filtered = PalindromeFilter.filterPalindromes(testInput);
  print(filtered);
}

List<String> filterPalindromes(List<String> input) =>
    PalindromeFilter.filterPalindromes(input);
