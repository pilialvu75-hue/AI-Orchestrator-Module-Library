"""Regression tests: a worker cannot self-assert independent local review."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_evidence import EvidenceError, verify_security_evidence  # noqa: E402
from library_review_attestation import PUBLIC_KEY_ENV  # noqa: E402
from library_source_integrity import payload_tree_sha256  # noqa: E402


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class SignedLocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "asset"
        self.source = self.base / "payload/src"
        self.source.mkdir(parents=True)
        (self.source / "diagnostics.dart").write_text(
            "String event() => 'safe';\n", encoding="utf-8")
        self.license = self.base / "provenance/LICENSE"
        self.license.parent.mkdir(parents=True)
        self.license.write_text("TEST-ONLY LICENSING FIXTURE\n", encoding="utf-8")
        self.sbom_path = self.base / "security/sbom.json"
        _write_json(self.sbom_path, {
            "bomFormat": "CycloneDX", "specVersion": "1.5", "components": [],
        })
        self.manifest = {
            "id": "diagnostics.local_test", "version": "0.1.0",
            "payload": {
                "type": "repository_path", "path": "payload/src",
                "sha256": payload_tree_sha256(self.source),
            },
            "provenance": {
                "source_commit": "a" * 40, "license": "MIT",
                "license_file": "provenance/LICENSE",
            },
            "security": {
                "reviewed": True, "reviewed_at": "2026-10-27T09:00:00Z",
                "known_vulnerabilities": 0,
                "review_report": "security/review.json", "sbom": "security/sbom.json",
            },
        }
        self.review_file = self.base / "security/review.json"
        self.statement = {
            "schema": "ai-orchestrator.library-review-authorization.v1",
            "asset_id": self.manifest["id"],
            "version": self.manifest["version"],
            "source_commit": "a" * 40,
            "payload_sha256": self.manifest["payload"]["sha256"],
            "sbom_sha256": hashlib.sha256(self.sbom_path.read_bytes()).hexdigest(),
            "license_file_sha256": hashlib.sha256(self.license.read_bytes()).hexdigest(),
            "reviewed_at": self.manifest["security"]["reviewed_at"],
            "reviewer_id": "independent-reviewer-test",
            "known_vulnerabilities": 0,
            "decision": "APPROVED",
        }
        self.private = self.root / "private.pem"
        self.public = self.root / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(self.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.private),
                        "-pubout", "-out", str(self.public)], check=True, capture_output=True)
        self.sign(self.statement)

    def sign(self, statement):
        message = (b"AI-ORCHESTRATOR-LOCAL-REVIEW-v1\n"
                   + json.dumps(statement, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=True).encode("ascii") + b"\n")
        raw = self.root / "statement.bin"
        sig = self.root / "statement.sig"
        raw.write_bytes(message)
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(self.private),
                        "-rawin", "-in", str(raw), "-out", str(sig)],
                       check=True, capture_output=True)
        report = {
            "schema": "ai-orchestrator.library-security-review.v1",
            "asset_id": self.manifest["id"], "version": self.manifest["version"],
            "source_commit": self.statement["source_commit"],
            "reviewed": True, "reviewed_at": statement["reviewed_at"],
            "reviewer_id": statement["reviewer_id"], "decision": "APPROVED",
            "known_vulnerabilities": 0,
            "sbom_sha256": statement["sbom_sha256"],
            "payload_sha256": statement["payload_sha256"],
            "independent_attestation": {
                "algorithm": "ed25519-openssl-v1",
                "statement": statement,
                "signature_base64": base64.b64encode(sig.read_bytes()).decode("ascii"),
            },
        }
        _write_json(self.review_file, report)
        return report

    def verify(self):
        with patch.dict(os.environ, {PUBLIC_KEY_ENV: self.public.read_text()}):
            verify_security_evidence(self.base, self.manifest)

    def test_independently_signed_exact_source_license_and_sbom_is_verifiable(self):
        self.verify()

    def test_unsiged_local_json_is_not_an_independent_security_review(self):
        report = json.loads(self.review_file.read_text())
        report.pop("independent_attestation")
        _write_json(self.review_file, report)
        with self.assertRaisesRegex(EvidenceError, "independent local security review"):
            self.verify()

    def test_absent_protected_public_key_blocks_even_correct_detached_signature(self):
        with patch.dict(os.environ, {PUBLIC_KEY_ENV: ""}):
            with self.assertRaisesRegex(EvidenceError, "key is not configured"):
                verify_security_evidence(self.base, self.manifest)

    def test_untrusted_public_key_does_not_authenticate_review(self):
        foreign = self.root / "other.pem"
        otherpub = self.root / "other-public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(foreign)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(foreign),
                        "-pubout", "-out", str(otherpub)], check=True, capture_output=True)
        with patch.dict(os.environ, {PUBLIC_KEY_ENV: otherpub.read_text()}):
            with self.assertRaisesRegex(EvidenceError, "signature does not authenticate"):
                verify_security_evidence(self.base, self.manifest)

    def test_worker_cannot_change_reviewer_id_without_another_signature(self):
        report = json.loads(self.review_file.read_text())
        report["reviewer_id"] = "attacker"
        report["independent_attestation"]["statement"]["reviewer_id"] = "attacker"
        _write_json(self.review_file, report)
        with self.assertRaisesRegex(EvidenceError, "signature does not authenticate"):
            self.verify()

    def test_source_license_or_sbom_mutation_invalidates_review(self):
        for path, extra in (
            (self.source / "diagnostics.dart", "// changed\n"),
            (self.license, "changed license\n"),
            (self.sbom_path, " "),
        ):
            original = path.read_bytes()
            with self.subTest(path=path):
                path.write_bytes(original + extra.encode("utf-8"))
                with self.assertRaises(EvidenceError):
                    self.verify()
            path.write_bytes(original)

    def test_signature_rejects_different_vulnerability_count_or_decision(self):
        original = self.statement.copy()
        for key, value in (("known_vulnerabilities", 1), ("decision", "REJECTED")):
            with self.subTest(field=key):
                self.statement[key] = value
                self.sign(self.statement)
                with self.assertRaises(EvidenceError):
                    self.verify()
                self.statement = original.copy()
        self.sign(self.statement)

    def _materialize_upstream_reference(self):
        # Emulate the newly acquired immutable upstream-reference payload.
        # The existing local-source fixture uses payload/src; upstream
        # snapshots pin the entire payload/ directory instead.
        digest = payload_tree_sha256(self.base / "payload")
        self.manifest["payload"] = {
            "type": "upstream_reference",
            "path": "payload",
            "sha256": digest,
            "upstream_repository": "https://github.com/example/upstream",
            "upstream_commit": "a" * 40,
        }
        self.statement["payload_sha256"] = digest
        self.sign(self.statement)

    def test_materialized_upstream_requires_independently_signed_review(self):
        self._materialize_upstream_reference()
        self.verify()
        raw = json.loads(self.review_file.read_text())
        raw.pop("independent_attestation")
        _write_json(self.review_file, raw)
        with self.assertRaisesRegex(EvidenceError, "independent local security review required"):
            self.verify()

    def test_materialized_upstream_rejects_tampered_source_and_wrong_key(self):
        self._materialize_upstream_reference()
        with patch.dict(os.environ, {PUBLIC_KEY_ENV: ""}):
            with self.assertRaisesRegex(EvidenceError, "key is not configured"):
                verify_security_evidence(self.base, self.manifest)
        (self.source / "diagnostics.dart").write_text("String event() => 'mutated';\n")
        with self.assertRaisesRegex(EvidenceError, "actual local source digest"):
            self.verify()

    def test_materialized_upstream_incomplete_pin_cannot_reuse_a_signed_report(self):
        self._materialize_upstream_reference()
        self.manifest["payload"].pop("path")
        with self.assertRaisesRegex(EvidenceError, "upstream source path must be payload"):
            self.verify()
        self.manifest["payload"]["path"] = "payload"
        self.manifest["payload"].pop("sha256")
        with self.assertRaisesRegex(EvidenceError, "valid SHA256 pin"):
            self.verify()

    def test_legacy_unmaterialized_upstream_evidence_is_not_retroactively_changed(self):
        # Existing certified upstream-reference manifests have no materialized
        # source or digest. This narrow backward-compatibility path must not
        # be mistaken for newly authenticated source code.
        self.manifest["payload"] = {
            "type": "upstream_reference",
            "upstream_repository": "https://github.com/example/legacy",
            "upstream_commit": "a" * 40,
        }
        report = json.loads(self.review_file.read_text())
        report.pop("independent_attestation")
        _write_json(self.review_file, report)
        self.verify()

    def test_signature_bytes_and_algorithms_are_strict(self):
        original = json.loads(self.review_file.read_text())
        for change in (
            {"algorithm": "rsa-sha256"},
            {"signature_base64": "abc"},
        ):
            report = json.loads(json.dumps(original))
            report["independent_attestation"].update(change)
            _write_json(self.review_file, report)
            with self.subTest(change=change), self.assertRaises(EvidenceError):
                self.verify()
        _write_json(self.review_file, original)


if __name__ == "__main__":
    unittest.main()
