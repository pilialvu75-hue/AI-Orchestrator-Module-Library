from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import materialize_upstream_evidence as evidence  # noqa: E402


class LibraryOwnedValidationScoreTest(unittest.TestCase):
    def test_successful_immutable_validation_replaces_researcher_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            upstream = root / "upstream"
            upstream.mkdir()
            subprocess.run(["git", "init"], cwd=upstream, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=upstream, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=upstream, check=True)
            (upstream / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=upstream, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=upstream, check=True, capture_output=True)
            source_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=upstream, check=True,
                capture_output=True, text=True,
            ).stdout.strip()

            asset = root / "asset"
            asset.mkdir()
            manifest = {
                "id": "ai.model_storage.example",
                "version": "0.1.0",
                "platforms": ["linux"],
                "provenance": {"source_commit": source_commit, "license": "MIT"},
                "validation": {
                    "score": 0.7319,
                    "tests_passed": False,
                    "validated_on": [],
                },
                "security": {"reviewed": False},
                "integration": {"known_constraints": []},
            }
            (asset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            deps_path = root / "deps.json"
            deps_path.write_text(json.dumps({"packages": []}), encoding="utf-8")

            with patch.object(evidence, "_query_osv", return_value=([], [])):
                result = evidence.materialize(
                    asset, upstream, deps_path, validated_on=["linux"]
                )

            updated = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
            validation = updated["validation"]
            self.assertEqual(1.0, result["validation_score"])
            self.assertEqual(1.0, validation["score"])
            self.assertEqual(0.7319, validation["researcher_recommendation_score"])
            self.assertEqual("library_immutable_validation_v1", validation["score_basis"])
            self.assertTrue(validation["tests_passed"])
            self.assertEqual(["linux"], validation["validated_on"])


if __name__ == "__main__":
    unittest.main()
