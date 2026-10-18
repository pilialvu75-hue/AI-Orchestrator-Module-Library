"""Independent source integrity checks for real local test/security attestations.

Existing upstream_reference assets are intentionally unaffected. Only an
actual local repository_path must match its test/security report AND the bytes.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_evidence import EvidenceError, verify_manifest_evidence, verify_security_evidence, verify_test_evidence
from library_pipeline import PipelineError, payload_tree_sha256, validate_payload
from library_source_integrity import payload_tree_sha256 as independently_calculated_digest


class PinnedLocalSourceEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "intake" / "module.test" / "0.1.0"
        self.source = self.base / "payload" / "src"
        self.source.mkdir(parents=True)
        (self.source / "lib.dart").write_text("int answer() => 42;\n", encoding="utf-8")
        self.pin = independently_calculated_digest(self.source)
        self.manifest = {
            "id": "module.test",
            "version": "0.1.0",
            "platforms": ["linux"],
            "provenance": {"source_commit": "a" * 40},
            "payload": {"type": "repository_path",
                        "path": "payload/src", "sha256": self.pin},
            "validation": {"tests_passed": True, "validated_on": ["linux"],
                           "test_report": "tests/test-report.json"},
            "security": {"reviewed": False},
        }
        self.test_report = {
            "schema": "ai-orchestrator.library-test-report.v1",
            "asset_id": "module.test",
            "version": "0.1.0",
            "source_commit": "a" * 40,
            "passed": True,
            "validated_on": ["linux"],
            "payload_sha256": self.pin,
        }
        self.write("tests/test-report.json", self.test_report)

    def write(self, path: str, payload: dict) -> None:
        location = self.base / path
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_valid_exact_bytes_and_report_allow_tested_but_not_security(self):
        self.assertEqual(payload_tree_sha256(self.source), self.pin)
        validate_payload(self.manifest, self.base)
        verify_test_evidence(self.base, self.manifest)
        verify_manifest_evidence(self.base, self.manifest)
        self.assertFalse(self.manifest["security"]["reviewed"])

    def test_modified_code_cannot_reuse_old_test_attestation(self):
        (self.source / "lib.dart").write_text("int answer() => 7;\n")
        with self.assertRaisesRegex(EvidenceError, "actual local source digest"):
            verify_test_evidence(self.base, self.manifest)

    def test_added_file_cannot_reuse_old_test_attestation(self):
        (self.source / "new.dart").write_text("var secret = 'new';\n")
        with self.assertRaisesRegex(EvidenceError, "actual local source digest"):
            verify_manifest_evidence(self.base, self.manifest)

    def test_missing_wrong_or_type_changed_report_digest_is_rejected(self):
        for value in (None, "", "wrong", "f" * 64, True):
            with self.subTest(value=value):
                report = dict(self.test_report)
                report["payload_sha256"] = value
                self.write("tests/test-report.json", report)
                with self.assertRaisesRegex(EvidenceError, "payload_sha256 differs"):
                    verify_test_evidence(self.base, self.manifest)

    def test_invalid_source_pin_cannot_pass_even_with_forged_receipt(self):
        self.manifest["payload"]["sha256"] = "f" * 64
        self.test_report["payload_sha256"] = "f" * 64
        self.write("tests/test-report.json", self.test_report)
        with self.assertRaisesRegex(EvidenceError, "actual local source digest"):
            verify_test_evidence(self.base, self.manifest)

    def test_missing_or_symlinked_local_source_is_rejected(self):
        (self.source / "lib.dart").unlink()
        (self.source / "lib.dart").symlink_to(self.base / "tests/test-report.json")
        with self.assertRaisesRegex(EvidenceError, "symlinks"):
            verify_test_evidence(self.base, self.manifest)

    def test_path_traversal_refused_before_file_read(self):
        for path in ("../../outside", "/tmp/outside", "payload/../tests",
                     "payload\\src", "payload/src/."):
            with self.subTest(path=path):
                self.manifest["payload"]["path"] = path
                with self.assertRaisesRegex(EvidenceError, "path"):
                    verify_test_evidence(self.base, self.manifest)

    def test_independent_security_report_must_bind_same_source_and_sbom(self):
        self.write("security/sbom.json", {
            "bomFormat": "CycloneDX", "specVersion": "1.5",
            "components": [],
        })
        sbom_bytes = (self.base / "security/sbom.json").read_bytes()
        report = {
            "schema": "ai-orchestrator.library-security-review.v1",
            "asset_id": "module.test",
            "version": "0.1.0",
            "source_commit": "a" * 40,
            "reviewed": True,
            "known_vulnerabilities": 0,
            "payload_sha256": self.pin,
            "sbom_sha256": hashlib.sha256(sbom_bytes).hexdigest(),
        }
        self.manifest["security"] = {
            "reviewed": True,
            "known_vulnerabilities": 0,
            "sbom": "security/sbom.json",
            "review_report": "security/review.json",
        }
        self.write("security/review.json", report)
        verify_security_evidence(self.base, self.manifest)

        (self.source / "lib.dart").write_text("int answer() => 0;\n")
        with self.assertRaisesRegex(EvidenceError, "actual local source digest"):
            verify_security_evidence(self.base, self.manifest)

        (self.source / "lib.dart").write_text("int answer() => 42;\n")
        report["payload_sha256"] = "f" * 64
        self.write("security/review.json", report)
        with self.assertRaisesRegex(EvidenceError, "payload_sha256 differs"):
            verify_security_evidence(self.base, self.manifest)

    def test_legacy_upstream_reference_test_evidence_not_retroactively_broken(self):
        self.manifest["payload"] = {
            "type": "upstream_reference",
            "upstream_repository": "https://github.com/example/legacy",
            "upstream_commit": "a" * 40,
        }
        report = dict(self.test_report)
        report.pop("payload_sha256")
        self.write("tests/test-report.json", report)
        verify_manifest_evidence(self.base, self.manifest)


if __name__ == "__main__":
    unittest.main()
