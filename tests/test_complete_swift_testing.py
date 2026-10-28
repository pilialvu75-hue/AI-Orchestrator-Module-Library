"""Fail-closed transition from real native CI receipts to TESTED (never CERTIFIED)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from complete_swift_testing import TestPromotionError, promote_tested  # noqa: E402
from library_evidence import verify_manifest_evidence  # noqa: E402
from library_source_integrity import payload_tree_sha256  # noqa: E402

SOURCE = ROOT / "intake/diagnostics.logging.avdlee.diagnostics/0.1.0"
TEMPLATE = ROOT / "tools/swift_adapters/diagnostics.logging.v1"


class TrustedSwiftTestCompletion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "intake" / "diagnostics.logging.avdlee.diagnostics" / "0.1.0"
        self.base.parent.mkdir(parents=True)
        shutil.copytree(SOURCE, self.base)
        bridge = self.root / "tools/swift_adapters/diagnostics.logging.v1"
        bridge.parent.mkdir(parents=True)
        shutil.copytree(TEMPLATE, bridge)
        # Mocked GitHub verifier test fixtures must represent a complete
        # source+adapter test pair with the CURRENT bridge template digest.
        # This does NOT modify real receipts or bypass production CI checks.
        native_proof_path = self.base / "provenance/swift-adapter.json"
        native_proof = json.loads(native_proof_path.read_text())
        native_proof["adapter_sha256"] = payload_tree_sha256(bridge)
        native_proof_path.write_text(json.dumps(native_proof))
        # The protected job first advances the working checkout to TESTED,
        # then runs this regression suite. Always reconstruct the original
        # discovered fixture explicitly, never inherit the live checkout state.
        self.original = json.loads((self.base / "manifest.json").read_text())
        self.original["status"] = "discovered"
        self.original["validation"] = {
            "score": 0.7618, "test_report": None, "tests_passed": False,
            "validated_at": None, "validated_on": [],
        }
        (self.base / "manifest.json").write_text(json.dumps(self.original))
        (self.base / "evidence/test-report.json").unlink(missing_ok=True)

    def test_exact_external_source_and_both_successful_jobs_become_tested(self):
        jobs = []
        def verify(run_id, name):
            jobs.append((run_id, name))
            return True
        result = promote_tested(self.root, verify=verify, now="2026-10-28T18:30:00Z")
        self.assertEqual(1, result["tested"])
        self.assertEqual("tested", result["status"])
        self.assertEqual(["verify_untrusted", "verify_adapter_untrusted"],
                         [name for _, name in jobs])
        actual = json.loads((self.base / "manifest.json").read_text())
        self.assertEqual(["macos"], actual["validation"]["validated_on"])
        self.assertTrue(actual["validation"]["tests_passed"])
        self.assertFalse(actual["security"]["reviewed"])
        self.assertEqual("upstream_reference", actual["payload"]["type"])
        verify_manifest_evidence(self.base, actual)
        self.assertEqual(0, promote_tested(self.root, verify=verify)["tested"])
        self.assertEqual(2, len(jobs))

    def test_a_forged_pass_is_never_written_if_github_refuses_it(self):
        with self.assertRaisesRegex(TestPromotionError, "not verified"):
            promote_tested(self.root, verify=lambda *_: False)
        self.assertEqual(self.original, json.loads((self.base / "manifest.json").read_text()))
        self.assertFalse((self.base / "evidence/test-report.json").exists())

    def test_bridge_digest_mutation_aborts_without_test_status(self):
        path = self.base / "provenance/swift-adapter.json"
        report = json.loads(path.read_text())
        report["adapter_sha256"] = "0" * 64
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(TestPromotionError, "canonical bridge"):
            promote_tested(self.root, verify=lambda *_: True)
        self.assertEqual("discovered", json.loads((self.base / "manifest.json").read_text())["status"])

    def test_upstream_source_mutation_aborts_before_trust_change(self):
        (self.base / "payload" / "Package.swift").write_text("mutated")
        with self.assertRaisesRegex(TestPromotionError, "source changed"):
            promote_tested(self.root, verify=lambda *_: True)
        self.assertEqual(self.original, json.loads((self.base / "manifest.json").read_text()))

    def test_tested_source_requires_fresh_bridge_evidence_after_template_change(self):
        verify = lambda _run, _job: True
        first = promote_tested(self.root, verify=verify, now="2026-10-28T18:30:00Z")
        self.assertEqual(1, first["tested"])
        old_report = json.loads((self.base / "evidence/test-report.json").read_text())
        self.assertEqual(0, promote_tested(self.root, verify=verify)["tested"])

        template = (self.root / "tools/swift_adapters/diagnostics.logging.v1"
                    / "Sources/AivexusDiagnosticsLoggingBridge.swift")
        template.write_text(template.read_text() + "\n// new guarded bridge revision\n")
        new_digest = payload_tree_sha256(template.parent.parent)
        proof_path = self.base / "provenance/swift-adapter.json"
        proof = json.loads(proof_path.read_text())
        proof["adapter_sha256"] = new_digest
        proof["github_run_id"] = "40788888888"
        proof_path.write_text(json.dumps(proof))

        revised = promote_tested(self.root, verify=verify, now="2026-10-28T19:00:00Z")
        self.assertEqual(1, revised["tested"])
        report = json.loads((self.base / "evidence/test-report.json").read_text())
        self.assertNotEqual(old_report["adapter_sha256"], report["adapter_sha256"])
        self.assertEqual(new_digest, report["adapter_sha256"])
        self.assertEqual("tested", json.loads((self.base / "manifest.json").read_text())["status"])
        self.assertEqual(0, promote_tested(self.root, verify=verify)["tested"])

    def test_upstream_test_failure_never_advances(self):
        path = self.base / "provenance/swift-probe.json"
        data = json.loads(path.read_text())
        data["result"] = "failed"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(TestPromotionError, "attestation"):
            promote_tested(self.root, verify=lambda *_: True)
        self.assertFalse((self.base / "evidence/test-report.json").exists())


if __name__ == "__main__":
    unittest.main()
