"""Privacy-hardening candidate must remain separate from immutable tested v0.1.0."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from library_source_integrity import payload_tree_sha256  # noqa: E402

BASE = ROOT / "intake/diagnostics.logging.dartlang.logging_adapter/0.1.1"
PRIOR = ROOT / "intake/diagnostics.logging.dartlang.logging_adapter/0.1.0"


class ClosedVocabularyCandidateTests(unittest.TestCase):
    def test_pinned_sources_and_lifecycle_are_failsafe(self):
        m = json.loads((BASE / "manifest.json").read_text())
        self.assertEqual("normalized", m["status"])
        self.assertFalse(m["security"]["reviewed"])
        self.assertFalse(m["validation"]["tests_passed"])
        self.assertEqual("repository_path", m["payload"]["type"])
        self.assertEqual(payload_tree_sha256(BASE / "payload/src"), m["payload"]["sha256"])
        self.assertEqual("2eaa1c85c6d116936bbfa461bd37173aa6ea6b3d841d58c2905ee421f39e0fab",
                         m["payload"]["sha256"])
        self.assertEqual("tested", json.loads((PRIOR / "manifest.json").read_text())["status"])
        self.assertNotEqual(
            payload_tree_sha256(PRIOR / "payload/src"),
            payload_tree_sha256(BASE / "payload/src"),
        )

    def test_preserves_exact_upstream_and_license_while_changing_adapter(self):
        current = BASE / "payload/src"
        original = PRIOR / "payload/src"
        for f in (original / "vendor/logging").rglob("*"):
            if f.is_file():
                copy = current / f.relative_to(original)
                self.assertEqual(f.read_bytes(), copy.read_bytes())
        self.assertEqual((BASE / "provenance/LICENSE").read_bytes(),
                         (current / "vendor/logging/LICENSE").read_bytes())
        self.assertEqual((current / "UPSTREAM_PROVENANCE.json").read_bytes(),
                         (original / "UPSTREAM_PROVENANCE.json").read_bytes())
        self.assertEqual(18, sum(1 for f in current.rglob("*") if f.is_file()))

    def test_only_enum_values_can_flow_to_logger(self):
        text = (BASE / "payload/src/lib/aivexus_external_logging.dart").read_text()
        self.assertIn("enum AivexusEventCode {", text)
        self.assertIn("void emit(AivexusEventCode code,", text)
        self.assertIn("_logger.log(level, code.wireCode);", text)
        self.assertNotIn("void emit(String eventCode,", text)
        self.assertNotIn("RegExp(r'^[a-z]", text)
        self.assertNotIn("print(", text)
        self.assertNotIn("dart:io", text)

    def test_no_claims_of_security_approval(self):
        m = json.loads((BASE / "manifest.json").read_text())
        self.assertIsNone(m["validation"]["test_report"])
        self.assertEqual([], m["validation"]["validated_on"])
        self.assertIsNone(m["security"]["review_report"])
        self.assertFalse((ROOT / "modules/diagnostics.logging.dartlang.logging_adapter").exists())


if __name__ == "__main__":
    unittest.main()
