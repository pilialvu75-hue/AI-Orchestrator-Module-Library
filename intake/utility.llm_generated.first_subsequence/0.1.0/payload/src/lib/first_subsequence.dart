library aivexus_first_subsequence;

int findSubsequence(List<int> haystack, List<int> needle) {
  if (needle.isEmpty) return 0;

  int n = haystack.length;
  int m = needle.length;

  for (int i = 0; i <= n - m; i++) {
    bool found = true;
    for (int j = 0; j < m; j++) {
      if (haystack[i + j] != needle[j]) {
        found = false;
        break;
      }
    }
    if (found) return i;
  }

  return -1;
}
