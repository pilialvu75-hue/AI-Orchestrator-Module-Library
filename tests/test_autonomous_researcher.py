import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from autonomous_researcher import select_candidate


class AutonomousResearcherTest(unittest.TestCase):
    def test_selects_high_priority_needed_first_party_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "catalog").mkdir()
            (root / ".airlab").mkdir()
            (root / "intake").mkdir()
            (root / "modules").mkdir()
            (root / "catalog/needs.json").write_text(json.dumps({"items": [
                {"capability_id": "low.cap", "priority": "low", "status": "needed"},
                {"capability_id": "high.cap", "priority": "high", "status": "needed"},
            ]}), encoding="utf-8")
            (root / ".airlab/first-party-sources.json").write_text(json.dumps({"sources": [
                {"repository": "owner/repo", "priority": "high", "candidates": [
                    {"capability_id": "low.cap", "component_path": "low", "kind": "module"},
                    {"capability_id": "high.cap", "component_path": "high", "kind": "module"},
                ]}
            ]}), encoding="utf-8")
            selected = select_candidate(root)
            self.assertEqual("high.cap", selected["need"]["capability_id"])
            self.assertEqual("high", selected["candidate"]["component_path"])

    def test_skips_already_present_asset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "catalog").mkdir()
            (root / ".airlab").mkdir()
            (root / "intake/high.cap.firstparty.repo/0.1.0").mkdir(parents=True)
            (root / "modules").mkdir()
            (root / "intake/high.cap.firstparty.repo/0.1.0/manifest.json").write_text("{}", encoding="utf-8")
            (root / "catalog/needs.json").write_text(json.dumps({"items": [
                {"capability_id": "high.cap", "priority": "high", "status": "needed"}
            ]}), encoding="utf-8")
            (root / ".airlab/first-party-sources.json").write_text(json.dumps({"sources": [
                {"repository": "owner/repo", "priority": "high", "candidates": [
                    {"capability_id": "high.cap", "component_path": "high", "kind": "module"}
                ]}
            ]}), encoding="utf-8")
            self.assertIsNone(select_candidate(root))


if __name__ == "__main__":
    unittest.main()
