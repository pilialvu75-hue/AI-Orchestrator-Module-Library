"""Verify autonomous source handoff cannot masquerade as tested or certified."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from autonomous_public_dart_gate import AutonomousSourceError, inspect, inspect_all
from library_source_integrity import payload_tree_sha256


class AutonomousPublicDartGateTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.target = self.root / "sandbox/researcher_public_dart/path"
        self.source = self.target / "payload/src"
        self.vendor = self.source / "vendor/path"
        (self.vendor / "lib").mkdir(parents=True)
        (self.source / "lib").mkdir()
        (self.source / "tool").mkdir()
        files = {
            "LICENSE": b"Redistribution and use in source and binary forms. BSD 3-Clause.",
            "pubspec.yaml": b"name: path\nversion: 1.9.1\n",
            "lib/path.dart": b"library path;\n",
        }
        for path, data in files.items():
            f = self.vendor / path
            f.parent.mkdir(exist_ok=True, parents=True)
            f.write_bytes(data)
        (self.source / "pubspec.yaml").write_text(
            "name: aivexus_external_path\ndependencies:\n  path:\n    path: vendor/path\n")
        (self.source / "lib/aivexus_external.dart").write_text(
            "import 'package:path/path.dart' as p;\n"
            "class Adapter { String join(String a,String b)=>p.posix.join(a,b); }\n")
        (self.source / "tool/self_test.dart").write_text(
            "import 'package:aivexus_external_path/aivexus_external.dart';\n"
            "void main(){if(Adapter().join('a','b')!='a/b') throw StateError('bad');}\n")
        h = {name: hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()
             for name, data in files.items()}
        self.meta = {
            "schema": "aivexus.researcher.autonomous-public-dart-intake.v1",
            "state": "NORMALIZED_NOT_TESTED", "package": "path",
            "package_version": "1.9.1", "capability_id": "platform.filesystem",
            "source_repository": "https://github.com/dart-lang/core",
            "source_subtree": "pkgs/path", "source_tag": "path-v1.9.1",
            "source_commit": "a" * 40, "source_license": "BSD-3-Clause",
            "source_git_blobs": h, "payload_sha256": payload_tree_sha256(self.source),
            "upstream_files": 3, "source_materialized": True,
            "independent_security_reviewed": False, "certification_authorized": False,
            "production_installation_authorized": False,
        }
        self._write()

    def _write(self):
        (self.target / "metadata.json").write_text(
            json.dumps(self.meta, sort_keys=True) + "\n")

    def test_source_receipt_is_byte_bound_not_security_approval(self):
        result = inspect(self.root, "path")
        self.assertTrue(result["source_materialized"])
        self.assertFalse(result["security_reviewed"])
        self.assertFalse(result["certification_authorized"])
        self.assertEqual(3, result["upstream_file_count"])
        self.assertEqual(1, inspect_all(self.root)["candidate_count"])

    def test_metadata_approval_claim_cannot_pass(self):
        self.meta["independent_security_reviewed"] = True
        self._write()
        with self.assertRaisesRegex(AutonomousSourceError, "self-certify"):
            inspect(self.root, "path")

    def test_pinned_original_blob_tampering_fails(self):
        (self.vendor / "lib/path.dart").write_text("library changed;\n")
        self.meta["payload_sha256"] = payload_tree_sha256(self.source)
        self._write()
        with self.assertRaisesRegex(AutonomousSourceError, "Git object modified"):
            inspect(self.root, "path")

    def test_unexpected_vendor_file_fails(self):
        (self.vendor / "payload.dart").write_text("unreviewed")
        self.meta["payload_sha256"] = payload_tree_sha256(self.source)
        self._write()
        with self.assertRaisesRegex(AutonomousSourceError, "injected"):
            inspect(self.root, "path")

    def test_unknown_package_fails_closed(self):
        other = self.root / "sandbox/researcher_public_dart/eval_exec"
        other.mkdir(parents=True)
        with self.assertRaisesRegex(AutonomousSourceError, "unrecognized"):
            inspect_all(self.root)

    def test_no_candidate_report_is_empty_without_certification(self):
        with tempfile.TemporaryDirectory() as p:
            summary = inspect_all(Path(p))
            self.assertEqual(0, summary["candidate_count"])
            self.assertFalse(summary["certification_authorized"])


if __name__ == "__main__":
    unittest.main()
