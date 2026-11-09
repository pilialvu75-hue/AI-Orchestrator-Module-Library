"""Regression tests: generated intake cannot claim Dart tests without CI evidence."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generated_dart_intake_candidate.py"
FILES = ("pubspec.yaml", "lib/aivexus_running_total.dart",
         "test/aivexus_running_total_test.dart", "generation.json")


class GeneratedDartIntakeEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        for name in FILES:
            path = self.package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")

    def generate(self, *, run=None, repository=None, passed=None):
        env = os.environ.copy()
        for key in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY",
                    "AIVEXUS_DART_TESTS_PASSED"):
            env.pop(key, None)
        if run is not None:
            env["GITHUB_RUN_ID"] = run
        if repository is not None:
            env["GITHUB_REPOSITORY"] = repository
        if passed is not None:
            env["AIVEXUS_DART_TESTS_PASSED"] = passed
        output = self.root / "candidate"
        subprocess.run([sys.executable, str(GENERATOR),
                        "--package", str(self.package), "--output", str(output),
                        "--source-commit", "test-source-sha"],
                       check=True, capture_output=True, text=True, env=env)
        return json.loads((output / "bundle.json").read_text())["manifest"]["validation"]

    def test_local_execution_does_not_claim_test_evidence(self):
        evidence = self.generate()
        self.assertFalse(evidence["tests_passed"])
        self.assertIsNone(evidence["test_report"])

    def test_ci_identity_without_success_does_not_claim_test_evidence(self):
        evidence = self.generate(
            run="12345", repository="pilialvu75-hue/AI-Orchestrator-Module-Library")
        self.assertFalse(evidence["tests_passed"])
        self.assertIsNone(evidence["test_report"])

    def test_unrelated_repository_cannot_supply_test_report(self):
        evidence = self.generate(
            run="12345", repository="another/repository", passed="true")
        self.assertFalse(evidence["tests_passed"])
        self.assertIsNone(evidence["test_report"])

    def test_verified_ci_success_attaches_current_run(self):
        evidence = self.generate(
            run="12345", repository="pilialvu75-hue/AI-Orchestrator-Module-Library",
            passed="true")
        self.assertTrue(evidence["tests_passed"])
        self.assertEqual(evidence["test_report"],
                         "https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library/actions/runs/12345")


if __name__ == "__main__":
    unittest.main()
