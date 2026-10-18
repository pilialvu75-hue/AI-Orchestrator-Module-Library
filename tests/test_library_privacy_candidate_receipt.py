"""No CI Boolean or self-asserted worker evidence can certify software."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.library_privacy_candidate_receipt import (
    ASSET_ID, VERSION, CHECKS, REPOSITORY, RECEIPT_SCHEMA,
    ReceiptError, accept_receipt,
)
from tools.library_pipeline import PipelineError

SOURCE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SHA = "a" * 40
RUN = 39127919606


class PrivacyCandidateReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.relative = Path("intake") / ASSET_ID / VERSION
        source = SOURCE_ROOT / self.relative
        destination = self.root / self.relative
        destination.parent.mkdir(parents=True)
        shutil.copytree(source, destination)
        self.base = destination
        self.manifest_file = destination / "manifest.json"
        manifest = self.manifest()
        manifest["status"] = "discovered"
        manifest["validation"] = {
            "score": 0, "tests_passed": False, "test_report": None,
            "validated_at": None, "validated_on": [],
        }
        manifest["security"]["reviewed"] = False
        self.manifest_file.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.receipt_file = self.root / "receipt.json"
        self.data = {
            "schema": RECEIPT_SCHEMA,
            "repository": REPOSITORY,
            "workflow_sha": WORKFLOW_SHA,
            "workflow_run_id": RUN,
            "workflow_run_attempt": 1,
            "asset_id": ASSET_ID,
            "version": VERSION,
            "source_commit": manifest["provenance"]["source_commit"],
            "payload_sha256": manifest["payload"]["sha256"],
            "validated_at": "2026-10-18T12:35:00+00:00",
            "checks": CHECKS,
            "validated_on": ["linux"],
            "passed": True,
        }
        self.save_receipt()

    def manifest(self):
        return json.loads(self.manifest_file.read_text(encoding="utf-8"))

    def save_receipt(self):
        self.receipt_file.write_text(json.dumps(self.data) + "\n", encoding="utf-8")

    def accept(self):
        return accept_receipt(
            root=self.root, path=self.receipt_file,
            workflow_sha=WORKFLOW_SHA,
            workflow_run_id=RUN, workflow_run_attempt=1,
        )

    def test_exact_bound_receipt_advances_through_real_pipeline_to_tested(self):
        result = self.accept()
        self.assertEqual(result["result"], "tested")
        manifest = self.manifest()
        self.assertEqual(manifest["status"], "tested")
        self.assertTrue(manifest["validation"]["tests_passed"])
        self.assertEqual(manifest["validation"]["validated_on"], ["linux"])
        self.assertEqual(manifest["validation"]["score"], 0.8)
        self.assertIs(manifest["security"]["reviewed"], False)
        self.assertIsNone(manifest["security"]["review_report"])
        report = json.loads(
            (self.base / "tests" / "dart-linux-ci-report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["workflow_run_id"], RUN)
        self.assertFalse(report["runtime_certified"])
        self.assertFalse(report["security_certified"])
        self.assertEqual(report["payload_sha256"], manifest["payload"]["sha256"])
        self.assertEqual(self.accept()["result"], "already_tested")

    def test_false_or_unbound_receipt_refused_without_lifecycle_mutation(self):
        for field, invalid in [
            ("passed", False),
            ("repository", "attacker/other"),
            ("workflow_sha", "b" * 40),
            ("workflow_run_id", RUN + 1),
            ("workflow_run_attempt", 2),
            ("asset_id", "unrelated"),
            ("payload_sha256", "f" * 64),
            ("source_commit", "f" * 40),
            ("validated_on", ["android"]),
            ("checks", ["echo fake pass"]),
        ]:
            with self.subTest(field=field):
                before = self.manifest_file.read_bytes()
                self.data[field] = invalid
                self.save_receipt()
                with self.assertRaisesRegex(ReceiptError, "not bound"):
                    self.accept()
                self.assertEqual(self.manifest_file.read_bytes(), before)
                self.data[field] = (
                    True if field == "passed" else {
                        "repository": REPOSITORY, "workflow_sha": WORKFLOW_SHA,
                        "workflow_run_id": RUN, "workflow_run_attempt": 1,
                        "asset_id": ASSET_ID,
                        "payload_sha256": self.manifest()["payload"]["sha256"],
                        "source_commit": self.manifest()["provenance"]["source_commit"],
                        "validated_on": ["linux"], "checks": CHECKS,
                    }[field]
                )

    def test_source_tamper_refused_even_when_run_metadata_looks_valid(self):
        source = self.base / "payload" / "src" / "lib" / "privacy_diagnostic_events.dart"
        source.write_text(source.read_text() + "\n// tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "SHA256 mismatch"):
            self.accept()
        self.assertEqual(self.manifest()["status"], "discovered")

    def test_review_gate_cannot_be_preapproved_by_test_admission(self):
        manifest = self.manifest()
        manifest["security"]["reviewed"] = True
        self.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ReceiptError, "review"):
            self.accept()

    def test_successful_report_is_immutable_after_receipt_consumption(self):
        self.accept()
        self.data["workflow_run_id"] = RUN + 1
        self.save_receipt()
        with self.assertRaisesRegex(ReceiptError, "not bound"):
            self.accept()
        self.assertEqual(self.manifest()["status"], "tested")


if __name__ == "__main__":
    unittest.main()
