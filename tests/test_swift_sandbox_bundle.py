"""Actual Swift source+adapter archives are sandbox-only and source-bound."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from swift_sandbox_bundle import SandboxBundleError, export, select  # noqa: E402
from library_source_integrity import payload_tree_sha256  # noqa: E402

SOURCE = ROOT / "intake/diagnostics.logging.avdlee.diagnostics/0.1.0"
BRIDGE = ROOT / "tools/swift_adapters/diagnostics.logging.v1"


class SwiftSandboxExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "intake/diagnostics.logging.avdlee.diagnostics/0.1.0"
        self.base.parent.mkdir(parents=True)
        shutil.copytree(SOURCE, self.base)
        template = self.root / "tools/swift_adapters/diagnostics.logging.v1"
        template.parent.mkdir(parents=True)
        shutil.copytree(BRIDGE, template)
        self.target = self.root / "reviewed-only-in-sandbox.tar.gz"
        self.manifest = json.loads((self.base / "manifest.json").read_text())

    def test_archive_is_real_swiftpm_source_and_never_certified(self):
        outcome = export(self.root, self.target)
        self.assertEqual(1, outcome["count"])
        self.assertTrue(outcome["sandbox_only"])
        self.assertFalse(outcome["production_approved"])
        self.assertFalse(outcome["certification_authorized"])
        self.assertGreater(outcome["file_count"], 80)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(),
                         outcome["bundle_sha256"])
        with tarfile.open(self.target, "r:gz") as tar:
            names = tar.getnames()
            self.assertIn("Package.swift", names)
            self.assertIn("Package.resolved", names)
            self.assertIn("LICENSE", names)
            self.assertIn("AivexusDiagnosticsLoggingBridge/AivexusDiagnosticsLoggingBridge.swift", names)
            self.assertIn("AivexusDiagnosticsBridgeTests/AivexusDiagnosticsBridgeTests.swift", names)
            self.assertIn("AIVEXUS_SANDBOX_ONLY.json", names)
            notice = json.load(tar.extractfile("AIVEXUS_SANDBOX_ONLY.json"))
            self.assertFalse(notice["production_approved"])
            self.assertFalse(notice["security_reviewed"])
            package = tar.extractfile("Package.swift").read().decode("utf-8")
            self.assertIn("AivexusDiagnosticsLoggingBridge", package)
        self.assertEqual(self.manifest, json.loads((self.base / "manifest.json").read_text()))
        self.assertEqual(self.manifest["payload"]["sha256"],
                         payload_tree_sha256(self.base / "payload"))

    def test_archives_are_deterministic_across_export_paths(self):
        first = export(self.root, self.target)
        second_path = self.root / "second-copy.tar.gz"
        other = export(self.root, second_path)
        self.assertEqual(first["bundle_sha256"], other["bundle_sha256"])
        self.assertEqual(self.target.read_bytes(), second_path.read_bytes())

    def test_changed_bridge_cannot_reuse_old_native_test_proof(self):
        template = (self.root / "tools/swift_adapters/diagnostics.logging.v1"
                    / "Sources/AivexusDiagnosticsLoggingBridge.swift")
        template.write_text(template.read_text() + "\n// unauthorized revision")
        with self.assertRaisesRegex(SandboxBundleError, "mismatch"):
            export(self.root, self.target)
        self.assertFalse(self.target.exists())

    def test_tampered_sbom_cannot_be_shipped(self):
        sbom = self.base / "evidence/sbom.cdx.json"
        sbom.write_text(sbom.read_text() + "\n")
        with self.assertRaisesRegex(SandboxBundleError, "SBOM"):
            export(self.root, self.target)

    def test_unreviewed_source_never_appears_in_certified_catalog(self):
        self.assertEqual(1, select(self.root)["count"])
        self.assertFalse((self.root / "modules").exists())
        self.manifest["status"] = "certified"
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        self.assertEqual(0, select(self.root)["count"])

    def test_mismatched_bridge_result_fails_closed(self):
        path = self.base / "provenance/swift-adapter.json"
        receipt = json.loads(path.read_text())
        receipt["result"] = "failed"
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(SandboxBundleError, "mismatch"):
            export(self.root, self.target)

    def test_original_payload_tampering_prevents_export(self):
        (self.base / "payload/Package.swift").write_text("mutated")
        with self.assertRaises(ValueError):
            export(self.root, self.target)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
