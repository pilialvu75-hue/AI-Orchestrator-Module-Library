import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_control_plane",
    ROOT / "tools" / "validate_control_plane.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

class ControlPlaneTests(unittest.TestCase):
    def test_repository_control_plane_is_valid(self):
        self.assertEqual(module.validate(ROOT), [])

if __name__ == "__main__":
    unittest.main()
