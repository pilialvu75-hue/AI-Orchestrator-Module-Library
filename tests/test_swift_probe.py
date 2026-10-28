"""The native Swift probe never authorizes module certification."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from library_source_integrity import payload_tree_sha256  # noqa: E402
from swift_probe import ProbeError, select, record  # noqa: E402


class SwiftProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "intake" / "diagnostics.logging.external" / "0.1.0"
        source = self.base / "payload"
        source.mkdir(parents=True)
        (source / "Package.swift").write_text("// swift-tools-version:6.0\n")
        (source / "Package.resolved").write_text(json.dumps({
            "version": 1, "object": {"pins": [{
                "package": "Example",
                "state": {"revision": "a" * 40, "version": "1.2.3"},
            }]}
        }))
        (source / "ExampleTests").mkdir()
        (source / "ExampleTests" / "ExampleTests.swift").write_text("import XCTest\n")
        self.digest = payload_tree_sha256(source)
        self.manifest = {
            "id": "diagnostics.logging.external",
            "version": "0.1.0",
            "status": "discovered",
            "languages": ["swift"],
            "platforms": ["macos", "ios"],
            "payload": {
                "type": "upstream_reference", "sha256": self.digest,
                "upstream_commit": "e" * 40,
                "upstream_repository": "https://github.com/example/project",
            },
            "provenance": {
                "source_commit": "e" * 40,
                "source_repository": "https://github.com/example/project",
                "license": "MIT",
            },
            "validation": {"tests_passed": False},
            "security": {"reviewed": False},
        }
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        (self.base / "provenance").mkdir()
        (self.base / "provenance" / "source-acquisition.json").write_text(json.dumps({
            "source_commit": "e" * 40,
            "payload_sha256": self.digest,
            "license_bytes_matched": True,
            "certification_authorized": False,
        }))

    @staticmethod
    def receipt(item, exit_code):
        return {
            "schema": "ai-orchestrator.swift-test-run.v1",
            "asset_id": item["asset_id"], "version": item["version"],
            "source_commit": item["source_commit"],
            "payload_sha256": item["payload_sha256"],
            "platform": "macos", "test_exit_code": exit_code,
        }

    def test_source_bound_selection_and_drift_fail_closed(self):
        self.assertEqual(1, select(self.root)["count"])
        (self.base / "payload" / "Package.swift").write_text("tampered")
        with self.assertRaisesRegex(ProbeError, "digest"):
            select(self.root)

    def test_success_records_no_certification_and_skips_same_commit(self):
        item = select(self.root)
        result = record(self.root, item, self.receipt(item, 0), "success", "40733333333")
        self.assertEqual("passed", result["result"])
        self.assertFalse(result["certification_authorized"])
        self.assertFalse(result["reviewed"])
        self.assertEqual(0, select(self.root)["count"])
        self.assertEqual(self.manifest, json.loads((self.base / "manifest.json").read_text()))

    def test_failure_recorded_once(self):
        item = select(self.root)
        result = record(self.root, item, self.receipt(item, 1), "failure", "40733333333")
        self.assertEqual("failed", result["result"])
        self.assertEqual(0, select(self.root)["count"])

    def test_forged_success_is_rejected_by_host_job_outcome(self):
        item = select(self.root)
        with self.assertRaisesRegex(ProbeError, "not corroborated"):
            record(self.root, item, self.receipt(item, 0), "failure", "40733333333")
        self.assertFalse((self.base / "provenance" / "swift-probe.json").exists())

    def test_unpinned_dependency_is_rejected(self):
        lockfile = self.base / "payload" / "Package.resolved"
        value = json.loads(lockfile.read_text())
        value["object"]["pins"][0]["state"]["revision"] = "main"
        lockfile.write_text(json.dumps(value))
        self.assertEqual(0, select(self.root)["count"])

    def test_unknown_license_is_rejected(self):
        self.manifest["provenance"]["license"] = "NOASSERTION"
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        self.assertEqual(0, select(self.root)["count"])


if __name__ == "__main__":
    unittest.main()
