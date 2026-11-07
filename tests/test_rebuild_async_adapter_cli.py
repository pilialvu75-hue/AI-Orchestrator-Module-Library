"""Fast CLI contract tests; full upstream rebuild requires a separate Dart integration run."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools/rebuild_async_adapter.py"


class RebuildAsyncAdapterCliTests(unittest.TestCase):
    def test_help_is_available_without_network(self):
        p = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("--source-commit", p.stdout)

    def test_rejects_unpinned_revision_without_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "artifact"
            p = subprocess.run([sys.executable, str(SCRIPT), "--source-commit",
                                "main", "--output", str(output)],
                               capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("40-character Git SHA", p.stderr)
            self.assertFalse(output.exists())

    def test_refuses_overwrite_before_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "existing"
            output.mkdir()
            p = subprocess.run([sys.executable, str(SCRIPT), "--source-commit",
                                "a" * 40, "--output", str(output)],
                               capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("refusing to overwrite", p.stderr)


if __name__ == "__main__":
    unittest.main()
