"""Review packets must be reproducible and never act as self-approval."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from library_privacy_review_packet import (  # noqa: E402
    ReviewPacketError, build_review_packet,
)
from library_source_integrity import payload_tree_sha256  # noqa: E402

REL = Path("intake/diagnostics.logging.library.privacy_events/0.1.0")


class PrivacyReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = self.root / REL
        self.candidate.parent.mkdir(parents=True)
        shutil.copytree(ROOT / REL, self.candidate)

    def _file(self, name):
        return self.candidate / name

    def _load(self, relative):
        return json.loads(self._file(relative).read_text(encoding="utf-8"))

    def _write(self, relative, data):
        self._file(relative).write_text(
            json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    def test_real_candidate_produces_deterministic_non_authorizing_request(self):
        first = build_review_packet(self.root)
        self.assertEqual(first, build_review_packet(self.root))
        self.assertEqual(first["status"], "INDEPENDENT_REVIEW_REQUIRED")
        self.assertEqual(first["source"]["tree_sha256"],
                         self._load("manifest.json")["payload"]["sha256"])
        self.assertEqual([r["platform"] for r in
                          first["test_claims_to_verify_independently"]["artifacts"]],
                         ["linux", "macos", "windows"])
        self.assertIs(first["test_claims_to_verify_independently"]["github_workflow_verified"], False)
        self.assertIs(first["security_reviewed"], False)
        self.assertIs(first["license_verified"], False)
        self.assertIs(first["module_certification_authorized"], False)
        self.assertIs(first["license_review"]["rights_granted_or_verified"], False)
        self.assertIs(first["security_review"]["reviewed_by_independent_authority"], False)
        self.assertIs(first["security_review"]["actual_vulnerability_scan_complete"], False)

    def test_changed_source_rejects_stale_test_proofs(self):
        source = self._file("payload/src/lib/privacy_diagnostic_events.dart")
        source.write_text(source.read_text() + "\n// unexpected source change\n")
        with self.assertRaisesRegex(ReviewPacketError, "pinned candidate verification failed"):
            build_review_packet(self.root)

    def test_report_cannot_invent_approval(self):
        for key in ("security_certified", "license_verified", "runtime_certified"):
            original = self._load("tests/dart-cross-platform-ci-report.json")
            report = dict(original)
            report[key] = True
            self._write("tests/dart-cross-platform-ci-report.json", report)
            with self.subTest(key=key), self.assertRaisesRegex(ReviewPacketError, "authority"):
                build_review_packet(self.root)
            self._write("tests/dart-cross-platform-ci-report.json", original)

    def test_tampered_platform_receipt_does_not_pass(self):
        name = "tests/dart-cross-platform-ci-report.json"
        original = self._load(name)
        corruptions = [
            {"validated_on": ["linux", "windows"]},
            {"payload_sha256": "a" * 64},
            {"source_commit": "f" * 40},
            {"workflow_sha": "invalid"},
            {"deterministic_adversarial_cases_per_platform": 0},
            {"workflow_run_id": True},
            {"platform_proofs": {"linux": original["platform_proofs"]["linux"]}},
            {"platform_proofs": {**original["platform_proofs"],
                                 "linux": {**original["platform_proofs"]["linux"],
                                           "evidence_sha256": "short"}}},
            {"platform_proofs": {**original["platform_proofs"],
                                 "linux": {**original["platform_proofs"]["linux"],
                                           "artifact_name": "another-workflow"}}},
        ]
        for i, part in enumerate(corruptions):
            self._write(name, {**original, **part})
            with self.subTest(i=i), self.assertRaises(ReviewPacketError):
                build_review_packet(self.root)
        self._write(name, original)

    def test_license_claim_does_not_equal_license_authorization(self):
        data = self._load("manifest.json")
        data["provenance"]["license"] = "MIT"
        data["provenance"]["license_file"] = "provenance/LICENSE"
        self._write("manifest.json", data)
        packet = build_review_packet(self.root)
        self.assertEqual(packet["license_review"]["declared_license"], "MIT")
        self.assertIs(packet["license_review"]["rights_granted_or_verified"], False)
        self.assertIs(packet["module_certification_authorized"], False)

    def test_report_does_not_change_untrusted_manifest(self):
        original = self._file("manifest.json").read_bytes()
        build_review_packet(self.root)
        self.assertEqual(original, self._file("manifest.json").read_bytes())

    def test_reviewed_flag_cannot_be_accepted_as_the_report_authority(self):
        manifest = self._load("manifest.json")
        manifest["security"]["reviewed"] = True
        self._write("manifest.json", manifest)
        with self.assertRaisesRegex(ReviewPacketError, "already approved"):
            build_review_packet(self.root)

    def test_unpinned_changed_source_with_forged_manifest_digest_still_refused(self):
        source = self._file("payload/src/lib/privacy_diagnostic_events.dart")
        source.write_text(source.read_text() + "\nvoid secretLeak() {}\n")
        manifest = self._load("manifest.json")
        manifest["payload"]["sha256"] = payload_tree_sha256(self._file("payload/src"))
        self._write("manifest.json", manifest)
        with self.assertRaisesRegex(ReviewPacketError, "pinned candidate verification failed"):
            build_review_packet(self.root)


if __name__ == "__main__":
    unittest.main()
