"""No-logic compiler repair regression tests for real Qwen Dart failures."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_real_llm_module_trials import _repair_missing_dart_math_import

SPEC = {"id": "max_run_length", "library_path": "lib/max_run_length.dart"}
SOURCE = """class MaxRunLength {
  static int longestRunLength(List<int> input) {
    if (input.isEmpty) return 0;
    int longest = 1;
    int current = 1;
    for (int i = 1; i < input.length; i++) {
      if (input[i] == input[i-1]) { current++; }
      else { longest = max(longest, current); current = 1; }
    }
    return max(longest, current);
  }
}
int longestRunLength(List<int> input) => MaxRunLength.longestRunLength(input);
"""
DIAGNOSTIC = ("dart analyze --fatal-infos failed: "
              "The method 'max' isn't defined for the type 'MaxRunLength'. "
              "undefined_method")


class CompilerDrivenImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "max_run_length/lib/max_run_length.dart"
        self.file.parent.mkdir(parents=True)
        self.file.write_text(SOURCE, encoding="utf-8")
        self.metadata = self.root / "max_run_length/generation.json"
        self.metadata.write_text(json.dumps({
            "generator": "aivexus-llm-candidate-v1",
            "model": "ollama-local/qwen2.5-coder:3b",
            "attempt": 2
        }), encoding="utf-8")

    def test_actual_undefined_max_diagnostic_auto_repaired_with_provenance(self):
        self.assertTrue(_repair_missing_dart_math_import(
            SPEC, self.root, DIAGNOSTIC))
        source = self.file.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("import 'dart:math' show max;\n"))
        self.assertEqual(source.split("\n", 1)[1], SOURCE)
        data = json.loads(self.metadata.read_text(encoding="utf-8"))
        self.assertEqual(data["compiler_driven_repairs"], [{
            "kind": "dart_math_missing_import_only",
            "symbols": ["max"],
            "diagnostic_sha256": hashlib.sha256(
                DIAGNOSTIC.encode("utf-8")).hexdigest(),
        }])
        self.assertEqual(data["attempt"], 2)
        self.assertFalse(_repair_missing_dart_math_import(
            SPEC, self.root, DIAGNOSTIC))

    def test_non_compiler_or_unrelated_errors_never_patch_source(self):
        for diagnostic in (
            "dart test failed due to wrong functional behavior",
            "The method 'max' isn't defined for the type 'OtherClass'.",
            "The method 'sqrt' isn't defined for the type 'MaxRunLength'.",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.file.write_text("int longestRunLength(List<int> x) => x.length;",
                                     encoding="utf-8")
                self.assertFalse(_repair_missing_dart_math_import(
                    SPEC, self.root, diagnostic))
                self.assertNotIn("dart:math", self.file.read_text())

    def test_respect_existing_dart_math_import_even_if_compiler_fails(self):
        self.file.write_text("import 'dart:math' as math;\n" + SOURCE,
                             encoding="utf-8")
        self.assertFalse(_repair_missing_dart_math_import(
            SPEC, self.root, DIAGNOSTIC))

    def test_min_diagnostic_is_supported_but_no_generated_function_logic(self):
        self.file.write_text(
            "int clampUpper(int a, int b) => min(a, b);\n", encoding="utf-8")
        diag = "Undefined name 'min' - undefined_identifier"
        self.assertTrue(_repair_missing_dart_math_import(SPEC, self.root, diag))
        self.assertEqual(self.file.read_text(encoding="utf-8"),
                         "import 'dart:math' show min;\n"
                         "int clampUpper(int a, int b) => min(a, b);\n")

    def test_no_missing_source_or_symlink_modification(self):
        self.file.unlink()
        self.assertFalse(_repair_missing_dart_math_import(
            SPEC, self.root, DIAGNOSTIC))
        self.file.symlink_to(self.metadata)
        self.assertFalse(_repair_missing_dart_math_import(
            SPEC, self.root, DIAGNOSTIC))


if __name__ == "__main__":
    unittest.main()
