"""Independent Swift review handoff stays source-bound and cannot self-certify."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from swift_review_packet import SwiftReviewPacketError, build_review_packet  # noqa: E402

SOURCE = ROOT / "intake/diagnostics.logging.avdlee.diagnostics/0.1.0"
BRIDGE = ROOT / "tools/swift_adapters/diagnostics.logging.v1"


class SwiftReviewPacketTests(unittest.TestCase):
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

    def test_deterministic_handoff_is_not_approval_and_contains_real_risks(self):
        before = (self.base / "manifest.json").read_bytes()
        packet = build_review_packet(self.root)
        self.assertEqual(packet, build_review_packet(self.root))
        self.assertEqual("INDEPENDENT_REVIEW_REQUIRED", packet["status"])
        self.assertIs(False, packet["certification_authorized"])
        self.assertIs(False, packet["production_approved"])
        self.assertIs(False, packet["reviewer_signature_present"])
        self.assertIs(False, packet["security_reviewed"])
        self.assertEqual(["macos"], packet["tested_adapter"]["platform_tested"])
        self.assertEqual(3, len(packet["security_evidence"]["static_source_privacy_findings"]))
        self.assertIn("adapter source is a separate overlay",
                      " ".join(packet["tested_adapter"]["adapter_risks"]))
        self.assertEqual(before, (self.base / "manifest.json").read_bytes())
        self.assertFalse((self.root / "modules").exists())

    def test_changed_original_license_is_rejected(self):
        license_file = self.base / "provenance/LICENSE"
        license_file.write_text(license_file.read_text() + "\nUNREVIEWED LICENSE CHANGE\n")
        with self.assertRaisesRegex(SwiftReviewPacketError, "license bytes differ"):
            build_review_packet(self.root)

    def test_changed_adapter_or_sbom_cannot_keep_old_handoff(self):
        bridge = self.root / "tools/swift_adapters/diagnostics.logging.v1/Sources/AivexusDiagnosticsLoggingBridge.swift"
        bridge.write_text(bridge.read_text() + "\n// changed without native retest\n")
        with self.assertRaises(SwiftReviewPacketError):
            build_review_packet(self.root)
        shutil.copyfile(
            BRIDGE / "Sources/AivexusDiagnosticsLoggingBridge.swift", bridge
        )
        sbom = self.base / "evidence/sbom.cdx.json"
        sbom.write_text(sbom.read_text() + "\n")
        with self.assertRaises(SwiftReviewPacketError):
            build_review_packet(self.root)

    def test_missing_privacy_finding_is_refused(self):
        path = self.base / "evidence/security-preflight.json"
        data = json.loads(path.read_text())
        data["source_privacy_findings"] = data["source_privacy_findings"][1:]
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(SwiftReviewPacketError, "critical process capture risks"):
            build_review_packet(self.root)

    def test_fake_security_approval_is_not_review_request(self):
        path = self.base / "manifest.json"
        data = json.loads(path.read_text())
        data["security"]["reviewed"] = True
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(SwiftReviewPacketError, "no eligible tested Swift source"):
            build_review_packet(self.root)


if __name__ == "__main__":
    unittest.main()
