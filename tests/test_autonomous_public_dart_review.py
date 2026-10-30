"""Review requests must remain read-only and never confer certification."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from autonomous_public_dart_review import collect, review  # noqa: E402


class AutomatedSourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = [
            "intake/utility.path_operations.external.dartlang.path/0.1.0",
            "sandbox/researcher_public_dart/path",
        ]
        for entry in paths:
            source = ROOT / entry
            target = self.root / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)

    def test_review_is_source_bound_read_only_and_not_authorized(self):
        manifest = (self.root / "intake/utility.path_operations.external.dartlang.path/0.1.0/manifest.json")
        before = manifest.read_bytes()
        request = review(self.root, "path")
        self.assertEqual("INDEPENDENT_REVIEW_REQUIRED", request["status"])
        self.assertEqual("tested", request["module_state"])
        self.assertEqual(31, request["source"]["original_upstream_files"])
        self.assertTrue(request["source"]["all_file_digests"])
        self.assertEqual("CycloneDX", request["dependency_inventory"]["cyclonedx_sbom"]["bomFormat"])
        self.assertEqual(["linux"], request["tested_evidence"]["verified_on"])
        self.assertFalse(request["security_reviewed"])
        self.assertFalse(request["certification_authorized"])
        self.assertFalse(request["reviewer_signature_present"])
        self.assertFalse(request["dependency_inventory"]["live_advisory_or_vulnerability_scan_completed"])
        self.assertEqual(before, manifest.read_bytes())
        self.assertEqual(request, review(self.root, "path"))

    def test_cannot_review_fake_approval(self):
        p = self.root / "intake/utility.path_operations.external.dartlang.path/0.1.0/manifest.json"
        obj = json.loads(p.read_text(encoding="utf-8"))
        obj["security"]["reviewed"] = True
        p.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            review(self.root, "path")

    def test_tampered_upstream_license_is_rejected(self):
        file = self.root / "intake/utility.path_operations.external.dartlang.path/0.1.0/provenance/LICENSE"
        file.write_text(file.read_text() + "\nforgery")
        with self.assertRaises(ValueError):
            review(self.root, "path")

    def test_empty_library_yields_no_fake_review_requests(self):
        with tempfile.TemporaryDirectory() as t:
            report = collect(Path(t))
            self.assertEqual(0, report["count"])
            self.assertFalse(report["certification_authorized"])


if __name__ == "__main__":
    unittest.main()
