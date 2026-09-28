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
from library_evidence import verify_manifest_evidence  # noqa: E402


class MaterializeUpstreamEvidenceTest(unittest.TestCase):
    def test_materializes_fail_closed_evidence_and_limits_platform_scope(self) -> None:
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
                ["git", "rev-parse", "HEAD"],
                cwd=upstream,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            asset = root / "intake" / "storage.local_db.example" / "0.1.0"
            asset.mkdir(parents=True)
            manifest = {
                "id": "storage.local_db.example",
                "version": "0.1.0",
                "platforms": ["android", "windows", "linux", "macos", "ios", "raspberry_pi"],
                "provenance": {"source_commit": source_commit, "license": "MIT"},
                "validation": {"score": 0.92, "tests_passed": False, "validated_on": []},
                "security": {"reviewed": False, "sbom": None},
                "integration": {"known_constraints": []},
            }
            (asset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            deps = {
                "packages": [
                    {"name": "collection", "version": "1.19.1", "source": "hosted"},
                    {"name": "fixture", "version": "0.1.0", "source": "root"},
                ]
            }
            deps_path = root / "deps.json"
            deps_path.write_text(json.dumps(deps), encoding="utf-8")

            osv_rows = [
                {
                    "package": {"ecosystem": "Pub", "name": "collection", "version": "1.19.1"},
                    "vulnerability_ids": [],
                }
            ]
            with patch.object(evidence, "_query_osv", return_value=(osv_rows, [])):
                result = evidence.materialize(asset, upstream, deps_path, validated_on=["linux"])

            self.assertEqual(["linux"], result["validated_on"])
            updated = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(["linux"], updated["platforms"])
            self.assertEqual(["linux"], updated["validation"]["validated_on"])
            self.assertTrue(updated["validation"]["tests_passed"])
            self.assertTrue(updated["security"]["reviewed"])
            self.assertEqual(0, updated["security"]["known_vulnerabilities"])
            self.assertIn(
                "Additional platform support requires separate immutable runtime validation",
                updated["integration"]["known_constraints"],
            )
            verify_manifest_evidence(asset, updated)

    def test_refuses_undeclared_runner_platform(self) -> None:
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
                ["git", "rev-parse", "HEAD"], cwd=upstream, check=True, capture_output=True, text=True
            ).stdout.strip()
            asset = root / "asset"
            asset.mkdir()
            manifest = {
                "id": "storage.local_db.example",
                "version": "0.1.0",
                "platforms": ["android", "windows"],
                "provenance": {"source_commit": source_commit, "license": "MIT"},
                "validation": {"score": 0.92, "tests_passed": False, "validated_on": []},
                "security": {"reviewed": False},
                "integration": {"known_constraints": []},
            }
            (asset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            deps_path = root / "deps.json"
            deps_path.write_text(json.dumps({"packages": []}), encoding="utf-8")

            with self.assertRaisesRegex(
                evidence.EvidenceMaterializationError,
                "validated platform was not declared by candidate: linux",
            ):
                evidence.materialize(asset, upstream, deps_path, validated_on=["linux"])

    def test_refuses_to_mark_reviewed_when_osv_reports_vulnerability(self) -> None:
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
                ["git", "rev-parse", "HEAD"], cwd=upstream, check=True, capture_output=True, text=True
            ).stdout.strip()

            asset = root / "asset"
            asset.mkdir()
            manifest = {
                "id": "storage.local_db.example",
                "version": "0.1.0",
                "platforms": ["linux"],
                "provenance": {"source_commit": source_commit, "license": "MIT"},
                "validation": {"score": 0.92, "tests_passed": False, "validated_on": []},
                "security": {"reviewed": False},
                "integration": {"known_constraints": []},
            }
            (asset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            deps_path = root / "deps.json"
            deps_path.write_text(
                json.dumps({"packages": [{"name": "bad", "version": "1.0.0", "source": "hosted"}]}),
                encoding="utf-8",
            )

            with patch.object(
                evidence,
                "_query_osv",
                return_value=(
                    [{"package": {"ecosystem": "Pub", "name": "bad", "version": "1.0.0"}, "vulnerability_ids": ["OSV-TEST"]}],
                    ["OSV-TEST"],
                ),
            ):
                with self.assertRaisesRegex(evidence.EvidenceMaterializationError, "OSV-TEST"):
                    evidence.materialize(asset, upstream, deps_path, validated_on=["linux"])

            unchanged = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(unchanged["security"]["reviewed"])


    def test_refuses_unresolved_license_for_non_allowlisted_source(self) -> None:
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
                ["git", "rev-parse", "HEAD"], cwd=upstream, check=True, capture_output=True, text=True
            ).stdout.strip()
            asset = root / "asset"
            asset.mkdir()
            manifest = {
                "id": "external.example",
                "version": "0.1.0",
                "platforms": ["linux"],
                "provenance": {
                    "source_commit": source_commit,
                    "source_repository": "https://github.com/example/external",
                    "license": "NOASSERTION",
                },
                "validation": {"score": 0.0, "tests_passed": False, "validated_on": []},
                "security": {"reviewed": False},
                "integration": {"known_constraints": []},
            }
            (asset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            deps_path = root / "deps.json"
            deps_path.write_text(json.dumps({"packages": []}), encoding="utf-8")
            with self.assertRaisesRegex(
                evidence.EvidenceMaterializationError,
                "not an immutable allowlisted first-party repository",
            ):
                evidence.materialize(asset, upstream, deps_path, validated_on=["linux"])


if __name__ == "__main__":
    unittest.main()
