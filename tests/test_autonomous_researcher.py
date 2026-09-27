import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from autonomous_researcher import materialize, select_candidate


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

    def test_materialize_uses_pinned_private_source_commit_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "intake").mkdir()
            pinned = "c65a8b8702930a40620dea34f1f14439532a5a9b"
            selected = {
                "need": {"capability_id": "ai.acceleration_backend", "targets": ["android"]},
                "source": {
                    "repository": "pilialvu75-hue/AI-Orchestrator-Core",
                    "source_commit": pinned,
                },
                "candidate": {"component_path": "native/android", "kind": "integration_bundle"},
                "asset_id": "ai.acceleration_backend.firstparty.ai-orchestrator-core",
            }
            path = materialize(root, selected)
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(pinned, manifest["payload"]["upstream_commit"])
            self.assertEqual(pinned, manifest["provenance"]["source_commit"])
            self.assertEqual("discovered", manifest["status"])

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
