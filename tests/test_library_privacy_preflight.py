"""Regression tests for read-only, source-bound candidate SBOM generation."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_privacy_preflight import CANDIDATE, PreflightError, security_preflight
from library_source_integrity import payload_tree_sha256


class PrivacyPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = self.root / CANDIDATE
        self.asset.parent.mkdir(parents=True)
        shutil.copytree(ROOT / CANDIDATE, self.asset)
        self.src = self.asset / "payload/src"

    def manifest(self):
        return json.loads((self.asset / "manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, data):
        (self.asset / "manifest.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def repin_source(self):
        value = self.manifest()
        value["payload"]["sha256"] = payload_tree_sha256(self.src)
        self.write_manifest(value)

    def test_real_candidate_has_source_hashes_and_no_certification(self):
        report = security_preflight(self.root)
        self.assertEqual(report["schema"], "ai-orchestrator.library-local-security-preflight.v1")
        self.assertEqual(report["asset_id"], "diagnostics.logging.library.privacy_events")
        self.assertEqual(report["payload_tree_sha256"], self.manifest()["payload"]["sha256"])
        self.assertRegex(report["test_report_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(report["sbom"]["bomFormat"], "CycloneDX")
        self.assertEqual(report["sbom"]["specVersion"], "1.5")
        self.assertEqual(report["third_party_pub_dependencies"], [])
        self.assertIs(report["security_reviewed"], False)
        self.assertIs(report["security_certified"], False)
        self.assertIs(report["license_verified"], False)
        self.assertIs(report["vulnerability_scanned"], False)
        self.assertIs(report["runtime_validated"], False)
        self.assertTrue(any(x["path"] == "lib/privacy_diagnostic_events.dart"
                            for x in report["source_files"]))
        self.assertTrue(all(len(x["sha256"]) == 64 for x in report["source_files"]))

    def test_changed_code_does_not_inherit_prior_security_inventory(self):
        (self.src / "lib/privacy_diagnostic_events.dart").write_text(
            "void exfiltrate() {}\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(PreflightError, "source digest differs"):
            security_preflight(self.root)

    def test_new_dependency_requires_independent_analysis_even_when_re_pinned(self):
        pubspec = self.src / "pubspec.yaml"
        original = pubspec.read_text()
        pubspec.write_text(original.replace("dependencies: {}", "dependencies:\n  http: ^1.0.0"))
        self.repin_source()
        with self.assertRaisesRegex(PreflightError, "independent dependency review"):
            security_preflight(self.root)

    def test_unexpected_dart_import_requires_review_even_when_re_pinned(self):
        code = self.src / "lib/privacy_diagnostic_events.dart"
        code.write_text("import 'dart:io';\n" + code.read_text(encoding="utf-8"))
        self.repin_source()
        with self.assertRaisesRegex(PreflightError, "unreviewed Dart import"):
            security_preflight(self.root)

    def test_disallow_aliasing_into_other_files_through_symlink(self):
        file = self.src / "bin/self_test.dart"
        file.unlink()
        file.symlink_to(self.src / "lib/privacy_diagnostic_events.dart")
        with self.assertRaisesRegex(PreflightError, "symlinks"):
            security_preflight(self.root)

    def test_cannot_turn_inventory_into_security_approval(self):
        value = self.manifest()
        value["security"]["reviewed"] = True
        self.write_manifest(value)
        with self.assertRaisesRegex(PreflightError, "independent reviewer"):
            security_preflight(self.root)

    def test_missing_ci_receipt_prevents_claiming_tested(self):
        report = self.asset / "tests/dart-linux-ci-report.json"
        report.unlink()
        with self.assertRaisesRegex(PreflightError, "missing CI test report"):
            security_preflight(self.root)


if __name__ == "__main__":
    unittest.main()
