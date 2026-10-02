import importlib.util
import json
import shutil
import tempfile
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

    def test_duplicate_automation_actor_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / ".airlab", root / ".airlab")
            registry_path = root / ".airlab/control-plane/automation-registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            duplicate = dict(registry["automations"][1])
            duplicate["automation_id"] = "duplicate-reviewer-actor"
            registry["automations"].append(duplicate)
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            errors = module.validate(root)
            self.assertTrue(any("duplicate automation actor_id" in item for item in errors))

    def test_mutating_automation_requires_registered_lane_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / ".airlab", root / ".airlab")
            registry_path = root / ".airlab/control-plane/automation-registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = registry["automations"][1]
            entry["owner_lane"] = "missing-lane"
            entry["allowed_operations"] = []
            entry["forbidden_takeover_rules"] = []
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            errors = module.validate(root)
            self.assertTrue(any("unknown owner_lane missing-lane" in item for item in errors))
            self.assertTrue(any("mutating automation requires allowed_operations" in item for item in errors))
            self.assertTrue(any("reviewer automation must forbid owner lane takeover" in item for item in errors))

if __name__ == "__main__":
    unittest.main()
