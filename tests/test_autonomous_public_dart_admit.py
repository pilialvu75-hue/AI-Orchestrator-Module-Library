"""The protected promotion records real Linux CI evidence, never security approval."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from autonomous_public_dart_admit import CONTRACTS, materialize, run  # noqa: E402
from library_evidence import verify_test_evidence  # noqa: E402
from library_source_integrity import payload_tree_sha256  # noqa: E402


class ProtectedAutoAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sandbox = self.root / "sandbox/researcher_public_dart/path"
        self.src = self.sandbox / "payload/src"
        self.vendor = self.src / "vendor/path"
        self.vendor.mkdir(parents=True)
        (self.src / "lib").mkdir()
        (self.src / "tool").mkdir()
        (self.vendor / "LICENSE").write_bytes(
            b"Redistribution and use in source and binary forms, with or without modification, are permitted.\n"
        )
        (self.vendor / "pubspec.yaml").write_text("name: path\nversion: 1.9.1\n")
        (self.src / "pubspec.yaml").write_text(
            "name: aivexus_external_path\nversion: 0.1.0\n"
        )
        (self.src / "lib/aivexus_external.dart").write_text(
            "import 'package:path/path.dart';\n"
        )
        (self.src / "tool/self_test.dart").write_text(
            "void main() { print('passed'); }\n"
        )
        self.digest = payload_tree_sha256(self.src)
        self.meta = {
            "schema": "aivexus.researcher.autonomous-public-dart-intake.v1",
            "package": "path",
            "package_version": "1.9.1",
            "source_repository": "https://github.com/dart-lang/core",
            "source_subtree": "pkgs/path",
            "source_tag": "path-v1.9.1",
            "source_commit": "a" * 40,
            "source_license": "BSD-3-Clause",
            "payload_sha256": self.digest,
        }
        self.sandbox.mkdir(parents=True, exist_ok=True)
        (self.sandbox / "metadata.json").write_text(json.dumps(self.meta))
        template = (ROOT / "intake/diagnostics.logging.dartlang.logging_adapter/0.1.1/manifest.json")
        template_destination = self.root / "intake/diagnostics.logging.dartlang.logging_adapter/0.1.1"
        template_destination.mkdir(parents=True)
        shutil.copyfile(template, template_destination / "manifest.json")

    @staticmethod
    def ci_receipt():
        return {
            "head": "b" * 40,
            "ci": {
                "id": 40998228229,
                "created_at": "2026-10-30T03:35:19Z",
                "updated_at": "2026-10-30T03:36:19Z",
            },
            "pr": {"number": 215},
        }

    def test_limited_contracts_not_falsely_platform_access(self):
        self.assertEqual("utility.path_operations", CONTRACTS["path"][0])
        self.assertNotEqual("platform.filesystem", CONTRACTS["path"][0])
        self.assertNotEqual("platform.process", CONTRACTS["fixnum"][0])

    def test_tested_intake_is_source_bound_without_certification(self):
        with patch("autonomous_public_dart_admit.inspect") as inspected:
            inspected.return_value = {"payload_sha256": self.digest}
            result = materialize(self.root, "path", self.ci_receipt())
        self.assertTrue(result["created"])
        base = self.root / result["path"]
        manifest = json.loads((base / "manifest.json").read_text())
        self.assertEqual("tested", manifest["status"])
        self.assertEqual(["linux"], manifest["validation"]["validated_on"])
        self.assertEqual("utility.path_operations.v1", manifest["connector"]["provides"][0]["contract_id"])
        self.assertEqual(self.digest, payload_tree_sha256(base / "payload/src"))
        self.assertFalse(manifest["security"]["reviewed"])
        self.assertIsNone(manifest["security"]["review_report"])
        self.assertFalse(result["certification_authorized"])
        verify_test_evidence(base, manifest)
        test_report = json.loads((base / "tests/dart-linux-ci-report.json").read_text())
        self.assertEqual(40998228229, test_report["evidence"]["github_run_id"])
        self.assertFalse(test_report["certification_authorized"])
        # A second attempt cannot duplicate a module.
        with patch("autonomous_public_dart_admit.inspect") as inspected:
            inspected.return_value = {"payload_sha256": self.digest}
            second = materialize(self.root, "path", self.ci_receipt())
        self.assertFalse(second["created"])

    def test_missing_ci_never_promotes_source(self):
        with patch("autonomous_public_dart_admit.source_proof", return_value=None):
            report = run(self.root)
        self.assertFalse(report["created"])
        self.assertEqual("no_immutable_dual_ci_proof", report["reason"])
        self.assertFalse((self.root / "intake/utility.path_operations.external.dartlang.path").exists())

    def test_no_source_no_mutation(self):
        with tempfile.TemporaryDirectory() as p:
            response = run(Path(p))
            self.assertFalse(response["created"])
            self.assertEqual("no_unadmitted_source", response["reason"])


if __name__ == "__main__":
    unittest.main()
