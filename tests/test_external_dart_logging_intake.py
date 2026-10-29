"""First materialized public-source Dart module: no metadata-only certification."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from library_evidence import EvidenceError, verify_test_evidence  # noqa: E402
from library_source_integrity import payload_tree_sha256  # noqa: E402

ASSET = ROOT / "intake/diagnostics.logging.dartlang.logging_adapter/0.1.0"
SANDBOX = ROOT / "sandbox/external_dart_logging"


class ExternalDartLoggingIntakeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ASSET / "manifest.json").read_text(encoding="utf-8"))

    def test_complete_upstream_and_adapter_bytes_are_materialized(self):
        source = ASSET / "payload/src"
        self.assertEqual("tested", self.manifest["status"])
        self.assertFalse(self.manifest["security"]["reviewed"])
        self.assertFalse((ROOT / "modules/diagnostics.logging.dartlang.logging_adapter").exists())
        self.assertEqual("repository_path", self.manifest["payload"]["type"])
        self.assertEqual(payload_tree_sha256(source), self.manifest["payload"]["sha256"])
        self.assertEqual(
            {p.relative_to(SANDBOX).as_posix() for p in SANDBOX.rglob("*") if p.is_file()},
            {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()},
        )
        for original in SANDBOX.rglob("*"):
            if original.is_file():
                self.assertEqual(original.read_bytes(),
                                 (source / original.relative_to(SANDBOX)).read_bytes())
        verify_test_evidence(ASSET, self.manifest)

    def test_upstream_blob_provenance_and_bsd_license(self):
        source = ASSET / "payload/src"
        upstream = json.loads((source / "UPSTREAM_PROVENANCE.json").read_text())
        self.assertEqual("https://github.com/dart-lang/core", upstream["repository"])
        self.assertEqual("8151b9f57fa3fee10421a19ce24470e143c0dee5", upstream["source_commit"])
        self.assertEqual("90ba3565cb83facd809fe382826f61904a7489c8", upstream["source_git_tree_sha"])
        self.assertEqual(13, upstream["upstream_source_file_count"])
        self.assertEqual(13, len(upstream["git_blob_sha_by_path"]))
        for name, sha in upstream["git_blob_sha_by_path"].items():
            p = source / "vendor/logging" / name
            self.assertTrue(p.is_file() and not p.is_symlink())
            data = p.read_bytes()
            self.assertEqual(
                hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest(), sha
            )
        self.assertEqual(
            (source / "vendor/logging/LICENSE").read_bytes(),
            (ASSET / "provenance/LICENSE").read_bytes(),
        )
        self.assertIn("BSD", self.manifest["provenance"]["license"])

    def test_exact_workflow_receipt_and_no_security_self_approval(self):
        report = json.loads((ASSET / "tests/dart-linux-ci-report.json").read_text())
        self.assertEqual(self.manifest["payload"]["sha256"], report["payload_sha256"])
        self.assertEqual(self.manifest["provenance"]["source_commit"], report["source_commit"])
        self.assertEqual(["linux"], report["validated_on"])
        self.assertEqual(40821013224, report["evidence"]["github_run_id"])
        self.assertEqual("c6e3b21da9a949e13ae5aecc363060b5c211b5c9",
                         report["evidence"]["github_commit"])
        self.assertTrue(report["passed"])
        self.assertIs(False, report["security_reviewed"])
        self.assertIs(False, report["certification_authorized"])

    def test_tampering_with_real_source_invalidates_test_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "asset"
            shutil.copytree(ASSET, local)
            f = local / "payload/src/lib/aivexus_external_logging.dart"
            f.write_text(f.read_text() + "\n// stale proof")
            with self.assertRaisesRegex(EvidenceError, "actual local source digest"):
                verify_test_evidence(local, self.manifest)


if __name__ == "__main__":
    unittest.main()
