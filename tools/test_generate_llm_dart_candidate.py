import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).with_name("generate_llm_dart_candidate.py")
spec = importlib.util.spec_from_file_location("candidate_generator", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CandidateValidationTest(unittest.TestCase):
    def setUp(self):
        self.files = {
            "pubspec.yaml": "name: original_module\nenvironment:\n  sdk: '>=3.3.0 <4.0.0'\n",
            "lib/original_module.dart": "int twice(int x) => x * 2;",
            "test/original_module_test.dart": "void main() {}",
        }

    def test_valid_package(self):
        self.assertEqual(module.validate_files({"files": self.files}), self.files)

    def test_rejects_traversal(self):
        self.files["../secrets.txt"] = "unsafe"
        with self.assertRaises(ValueError):
            module.validate_files({"files": self.files})

    def test_rejects_scripts(self):
        self.files["build.sh"] = "exit 0"
        with self.assertRaises(ValueError):
            module.validate_files({"files": self.files})

    def test_rejects_missing_tests(self):
        self.files.pop("test/original_module_test.dart")
        with self.assertRaises(ValueError):
            module.validate_files({"files": self.files})

    def test_rejects_extra_model_fields(self):
        with self.assertRaises(ValueError):
            module.validate_files({"files": self.files, "command": "sh"})

    def test_no_credentials_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                module.generate("Build a module", Path(tmp) / "out",
                                endpoint="https://example.org/v1/chat/completions",
                                model="test", api_key="")


if __name__ == "__main__":
    unittest.main()
