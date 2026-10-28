"""Real source-bound Swift bridge builder regression tests (no certification)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "tools"))

from library_source_integrity import payload_tree_sha256  # noqa: E402
from swift_adapter import AdapterError, RESULT_SCHEMA, plan, stage, record  # noqa: E402
from swift_probe import TOOLCHAIN_PROFILE  # noqa: E402


class SwiftAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        src_templates = REPOSITORY / "tools" / "swift_adapters" / "diagnostics.logging.v1"
        dst_templates = self.root / "tools" / "swift_adapters" / "diagnostics.logging.v1"
        dst_templates.parent.mkdir(parents=True)
        shutil.copytree(src_templates, dst_templates)
        self.base = self.root / "intake" / "diagnostics.logging.sample" / "0.1.0"
        source = self.base / "payload"
        (source / "Sources" / "Logging").mkdir(parents=True)
        (source / "Sources" / "Logging" / "DiagnosticsLogger.swift").write_text(
            "public final class DiagnosticsLogger: Sendable {}\n"
            "public static func setup() throws {}\n"
            "public static func log(message: String) {}\n"
            "public static func isSetUp() -> Bool { true }\n"
        )
        (source / "Package.swift").write_text(
            '// swift-tools-version:6.0\n'
            'import PackageDescription\n'
            'let package = Package(\n'
            '  name: "Diagnostics",\n'
            '  products: [\n'
            '    .library(name: "Diagnostics", targets: ["Diagnostics"])\n'
            '  ],\n'
            '    targets: [\n'
            '        .target(name: "Diagnostics", path: "Sources")\n'
            '    ])\n'
        )
        self.sha = "a" * 40
        self.hash = payload_tree_sha256(source)
        self.manifest = {
            "id": "diagnostics.logging.sample", "version": "0.1.0",
            "status": "discovered", "capabilities": ["diagnostics.logging"],
            "platforms": ["macos", "ios"], "languages": ["swift"],
            "payload": {
                "type": "upstream_reference",
                "sha256": self.hash,
                "upstream_commit": self.sha,
                "upstream_repository": "https://github.com/sample/diagnostics",
            },
            "provenance": {
                "source_commit": self.sha,
                "source_repository": "https://github.com/sample/diagnostics",
                "license": "MIT",
            },
            "connector": {
                "provides": [
                    {"capability_id": "diagnostics.logging", "contract_id": "diagnostics.logging.v1"}
                ]
            },
            "validation": {"tests_passed": False},
            "security": {"reviewed": False},
        }
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        (self.base / "provenance").mkdir()
        (self.base / "provenance" / "swift-probe.json").write_text(json.dumps({
            "result": "passed", "source_commit": self.sha,
            "payload_sha256": self.hash, "toolchain_profile": TOOLCHAIN_PROFILE,
            "certification_authorized": False,
        }))

    @staticmethod
    def result(item: dict, code: int) -> dict:
        keys = ("asset_id", "version", "source_commit", "payload_sha256",
                "adapter_sha256", "contract_id", "platform", "toolchain_profile")
        return {"schema": RESULT_SCHEMA, **{key: item[key] for key in keys},
                "test_exit_code": code}

    def test_stage_real_bridge_without_mutating_immutable_source(self):
        item = plan(self.root)
        self.assertEqual(1, item["count"])
        output = self.root / "staged"
        stage(self.root, item, output)
        pkg = (output / "Package.swift").read_text()
        self.assertIn('AivexusDiagnosticsLoggingBridge", dependencies: ["Diagnostics"]', pkg)
        self.assertIn("AivexusDiagnosticsBridgeTests", pkg)
        bridge = (output / "AivexusDiagnosticsLoggingBridge"
                  / "AivexusDiagnosticsLoggingBridge.swift").read_text()
        self.assertIn("DiagnosticsLogger.log(message:", bridge)
        self.assertIn("redactKnownSecrets", bridge)
        self.assertEqual(self.hash, payload_tree_sha256(self.base / "payload"))
        self.assertEqual(self.manifest, json.loads((self.base / "manifest.json").read_text()))

    def test_success_is_source_bound_but_not_certified(self):
        item = plan(self.root)
        r = record(self.root, item, self.result(item, 0), "success", "40777777777")
        self.assertEqual("passed", r["result"])
        self.assertFalse(r["certification_authorized"])
        self.assertFalse(r["independent_security_reviewed"])
        self.assertEqual(0, plan(self.root)["count"])
        self.assertFalse(json.loads((self.base / "manifest.json").read_text())["validation"]["tests_passed"])

    def test_reject_forged_success(self):
        item = plan(self.root)
        with self.assertRaisesRegex(AdapterError, "contradicts"):
            record(self.root, item, self.result(item, 0), "failure", "40777777777")
        self.assertFalse((self.base / "provenance" / "swift-adapter.json").exists())

    def test_reject_wrong_template_or_upstream_digest(self):
        item = plan(self.root)
        invalid = dict(item, adapter_sha256="0" * 64)
        with self.assertRaisesRegex(AdapterError, "changed"):
            stage(self.root, invalid, self.root / "build")
        template = self.root / "tools" / "swift_adapters" / "diagnostics.logging.v1" / "Sources" / "AivexusDiagnosticsLoggingBridge.swift"
        template.write_text("tampered")
        with self.assertRaisesRegex(AdapterError, "changed"):
            stage(self.root, item, self.root / "build")

    def test_source_drift_never_reuses_pass_receipt(self):
        self.assertEqual(1, plan(self.root)["count"])
        (self.base / "payload" / "Package.swift").write_text("tampered")
        with self.assertRaisesRegex(AdapterError, "digest mismatch"):
            plan(self.root)

    def test_unverified_or_missing_upstream_probe_cannot_start_builder(self):
        path = self.base / "provenance" / "swift-probe.json"
        proof = json.loads(path.read_text())
        proof["result"] = "failed"
        path.write_text(json.dumps(proof))
        self.assertEqual(0, plan(self.root)["count"])

    def test_tested_candidate_can_build_new_adapter_revision(self):
        self.manifest["status"] = "tested"
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        old_plan = plan(self.root)
        self.assertEqual(1, old_plan["count"])
        record(self.root, old_plan, self.result(old_plan, 0), "success", "40777777777")
        self.assertEqual(0, plan(self.root)["count"])
        new_bridge = (self.root / "tools/swift_adapters/diagnostics.logging.v1"
                      / "Sources/AivexusDiagnosticsLoggingBridge.swift")
        new_bridge.write_text(new_bridge.read_text() + "\n// explicit opt-in revision\n")
        next_plan = plan(self.root)
        self.assertEqual(1, next_plan["count"])
        self.assertNotEqual(old_plan["adapter_sha256"], next_plan["adapter_sha256"])

    def test_new_template_version_is_retested_not_assumed_valid(self):
        item = plan(self.root)
        record(self.root, item, self.result(item, 1), "failure", "40777777777")
        self.assertEqual(0, plan(self.root)["count"])
        template = (self.root / "tools" / "swift_adapters" / "diagnostics.logging.v1"
                    / "Tests" / "AivexusDiagnosticsBridgeTests.swift")
        template.write_text(template.read_text() + "\n// new test\n")
        self.assertEqual(1, plan(self.root)["count"])


if __name__ == "__main__":
    unittest.main()
