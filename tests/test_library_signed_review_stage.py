"""End-to-end synthetic-key tests; never a real independent approval."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_pipeline import AssetRef, promote
from library_protected_review_sign import sign
from library_signed_review_stage import stage
from library_source_integrity import payload_tree_sha256

ENV = "LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM"
ASSET = "utility.int64_arithmetic.external.dartlang.fixnum"
VERSION = "0.1.0"


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


class SignedReviewStagingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "intake" / ASSET / VERSION
        payload = self.base / "payload" / "src"
        payload.mkdir(parents=True)
        (payload / "pubspec.yaml").write_text("name: synthetic_fixnum_fixture\n", encoding="utf-8")
        (payload / "lib").mkdir()
        (payload / "lib" / "math.dart").write_text("int add(int a,int b)=>a+b;\n", encoding="utf-8")
        license_path = self.base / "provenance" / "LICENSE"
        license_path.parent.mkdir()
        license_path.write_text("TEST LICENSE FIXTURE\n", encoding="utf-8")
        sha = payload_tree_sha256(payload)
        self.commit = "a" * 40
        self.manifest = {
            "id": ASSET, "version": VERSION, "name": "Test fixture",
            "kind": "module", "status": "tested",
            "platforms": ["linux"], "capabilities": ["utility.int64_arithmetic"],
            "provenance": {"origin": "researcher",
                           "source_repository": "https://github.com/dart-lang/core",
                           "source_commit": self.commit, "license": "BSD-3-Clause",
                           "license_file": "provenance/LICENSE"},
            "payload": {"type": "repository_path", "path": "payload/src", "sha256": sha},
            "connector": {"standard": "ai-orchestrator-lego", "standard_version": "1.0.0",
                          "provides": [{"capability_id": "utility.int64_arithmetic",
                                        "contract_id": "utility.int64_arithmetic.v1"}]},
            "validation": {"tests_passed": True, "score": 0.8,
                           "validated_at": "2026-11-17T12:00:00Z",
                           "validated_on": ["linux"], "test_report": "tests/ci-report.json"},
            "security": {"reviewed": False, "reviewed_at": None,
                         "known_vulnerabilities": None,
                         "sbom": None, "review_report": None},
        }
        dump(self.base / "manifest.json", self.manifest)
        dump(self.base / "tests" / "ci-report.json", {
            "schema": "ai-orchestrator.library-test-report.v1",
            "asset_id": ASSET, "version": VERSION,
            "source_commit": self.commit, "payload_sha256": sha,
            "passed": True, "validated_on": ["linux"],
        })
        dump(self.root / "catalog" / "index.json", {
            "schema_version": 1, "catalog_version": "1.0.0",
            "updated_at": "2026-11-17T12:00:00Z", "assets": [],
        })
        self.sbom = self.root / "sbom.json"
        dump(self.sbom, {"bomFormat": "CycloneDX", "specVersion": "1.5",
                         "components": [{"type": "library", "name": "fixnum",
                                         "version": "1.1.1",
                                         "purl": "pkg:pub/fixnum@1.1.1"}]})
        self.private = self.root / "private.pem"
        self.public = self.root / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(self.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.private),
                        "-pubout", "-out", str(self.public)],
                       check=True, capture_output=True)
        self.statement = {
            "schema": "ai-orchestrator.library-review-authorization.v1",
            "asset_id": ASSET, "version": VERSION, "source_commit": self.commit,
            "payload_sha256": sha,
            "sbom_sha256": hashlib.sha256(self.sbom.read_bytes()).hexdigest(),
            "license_file_sha256": hashlib.sha256(license_path.read_bytes()).hexdigest(),
            "reviewed_at": "2026-11-17T13:00:00Z",
            "reviewer_id": "synthetic-reviewer-only", "known_vulnerabilities": 0,
            "decision": "APPROVED",
        }
        self.attestation = self.root / "attestation.json"
        dump(self.attestation, sign(self.statement, self.private.read_text()))

    def invoke(self, *, apply=False):
        with patch.dict(os.environ, {ENV: self.public.read_text()}):
            return stage(self.root, ASSET, VERSION, self.sbom, self.attestation,
                         self.root / "stage", apply=apply)

    def test_signed_review_stages_without_mutating_real_intake(self):
        before = (self.base / "manifest.json").read_bytes()
        outcome = self.invoke()
        self.assertTrue(outcome["signature_checked"])
        self.assertFalse(outcome["applied_to_intake"])
        self.assertEqual((self.base / "manifest.json").read_bytes(), before)
        self.assertFalse((self.base / "evidence").exists())
        self.assertFalse((self.root / "stage" / ASSET / VERSION).exists())

    def test_real_gate_allows_synthetic_signed_review_to_be_promoted(self):
        self.invoke(apply=True)
        staged = json.loads((self.base / "manifest.json").read_text())
        self.assertTrue(staged["security"]["reviewed"])
        with patch.dict(os.environ, {ENV: self.public.read_text()}):
            dry_run = promote(self.root, AssetRef(ASSET, VERSION), dry_run=True)
            self.assertEqual(dry_run["result"], "dry_run_ok")
            promoted = promote(self.root, AssetRef(ASSET, VERSION))
            self.assertEqual(promoted["result"], "promoted")
            self.assertTrue((self.root / "modules" / ASSET / VERSION / "manifest.json").is_file())

    def test_without_protected_key_review_is_rejected(self):
        with patch.dict(os.environ, {ENV: ""}):
            with self.assertRaises(ValueError):
                stage(self.root, ASSET, VERSION, self.sbom, self.attestation,
                      self.root / "stage")
        self.assertFalse((self.base / "evidence").exists())

    def test_wrong_trusted_key_is_rejected(self):
        foreign = self.root / "wrong.pem"
        foreign_public = self.root / "wrong.pub"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(foreign)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(foreign),
                        "-pubout", "-out", str(foreign_public)],
                       check=True, capture_output=True)
        with patch.dict(os.environ, {ENV: foreign_public.read_text()}):
            with self.assertRaises(Exception):
                stage(self.root, ASSET, VERSION, self.sbom, self.attestation,
                      self.root / "stage")
        self.assertFalse((self.base / "evidence").exists())

    def test_sbom_tamper_is_rejected(self):
        self.sbom.write_bytes(self.sbom.read_bytes() + b" ")
        with self.assertRaises(Exception):
            self.invoke()
        self.assertFalse((self.base / "evidence").exists())

    def test_source_tamper_is_rejected(self):
        (self.base / "payload" / "src" / "lib" / "math.dart").write_text("int add(int a,int b)=>0;\n")
        with self.assertRaises(Exception):
            self.invoke()
        self.assertFalse((self.base / "evidence").exists())

    def test_attestation_reviewer_and_decision_tamper_are_rejected(self):
        original = json.loads(self.attestation.read_text())
        for field, value in (("reviewer_id", "attacker"), ("decision", "REJECTED")):
            with self.subTest(field=field):
                tampered = json.loads(json.dumps(original))
                tampered["statement"][field] = value
                dump(self.attestation, tampered)
                with self.assertRaises(Exception):
                    self.invoke()
                self.assertFalse((self.base / "evidence").exists())

    def test_untrusted_staging_location_rejected(self):
        with patch.dict(os.environ, {ENV: self.public.read_text()}):
            with self.assertRaises(ValueError):
                stage(self.root, ASSET, VERSION, self.sbom, self.attestation,
                      self.base / "inside")

    def test_repeat_apply_is_rejected(self):
        self.invoke(apply=True)
        with self.assertRaises(ValueError):
            self.invoke(apply=True)


if __name__ == "__main__":
    unittest.main()
