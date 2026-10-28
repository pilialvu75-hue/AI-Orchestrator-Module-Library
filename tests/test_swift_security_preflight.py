"""Source-locked Swift preflight is not an independent security approval."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from swift_security_preflight import SwiftPreflightError, analyze  # noqa: E402

EXTERNAL = ROOT / "intake/diagnostics.logging.avdlee.diagnostics/0.1.0"


class SwiftSecurityPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "intake/diagnostics.logging.avdlee.diagnostics/0.1.0"
        self.base.parent.mkdir(parents=True)
        shutil.copytree(EXTERNAL, self.base)
        self.calls = []

    def _osv(self, queries):
        self.calls.append(queries)
        return [{"vulns": []} for _ in queries]

    @staticmethod
    def _license(repository, revision):
        return "license", b"MIT License\n\nPermission is hereby granted, free of charge."

    def test_real_swiftpm_lockfile_becomes_bounded_sbom_without_approval(self):
        result = analyze(self.root, scan=self._osv, license_lookup=self._license,
                         now="2026-10-28T18:40:00Z")
        self.assertEqual(1, result["scanned"])
        self.assertEqual(0, result["known_osv_match_count"])
        self.assertEqual(1, len(self.calls))
        self.assertGreater(len(self.calls[0]), 1)
        report = json.loads((self.base / "evidence/security-preflight.json").read_text())
        sbom = json.loads((self.base / "evidence/sbom.cdx.json").read_text())
        self.assertEqual("CycloneDX", sbom["bomFormat"])
        self.assertTrue(sbom["components"])
        self.assertFalse(report["reviewed"])
        self.assertFalse(report["certification_authorized"])
        self.assertTrue(report["review_required_reasons"])
        self.assertEqual(0, analyze(self.root, scan=self._osv,
                                    license_lookup=self._license)["scanned"])
        self.assertEqual(1, len(self.calls))
        manifest = json.loads((self.base / "manifest.json").read_text())
        self.assertFalse(manifest["security"]["reviewed"])

    def test_osv_vulnerability_never_becomes_a_false_security_pass(self):
        def vulnerable(queries):
            rows = [{"vulns": []} for _ in queries]
            rows[-1] = {"vulns": [{"id": "GHSA-test-security-case"}]}
            return rows
        analyze(self.root, scan=vulnerable, license_lookup=self._license)
        report = json.loads((self.base / "evidence/security-preflight.json").read_text())
        self.assertIn("GHSA-test-security-case", report["osv_vulnerability_ids"])
        self.assertIn("known_dependency_vulnerabilities", report["review_required_reasons"])
        self.assertFalse(report["reviewed"])

    def test_failed_osv_never_writes_security_artifacts(self):
        def unavailable(_queries):
            raise SwiftPreflightError("OSV unavailable")
        with self.assertRaisesRegex(SwiftPreflightError, "unavailable"):
            analyze(self.root, scan=unavailable, license_lookup=self._license)
        self.assertFalse((self.base / "evidence/security-preflight.json").exists())

    def test_unpinned_or_changed_source_fails_closed(self):
        (self.base / "payload/Package.swift").write_text("mutated")
        with self.assertRaisesRegex(SwiftPreflightError, "source pin"):
            analyze(self.root, scan=self._osv, license_lookup=self._license)


if __name__ == "__main__":
    unittest.main()
