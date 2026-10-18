"""Pinned source-license evidence for existing Mia first-party intake candidates.

These tests prove license attribution only. They NEVER self-assert functional
testing, vulnerability-free status, target support, or certification.
"""
import hashlib
import json
import unittest
from pathlib import Path

from tools.library_intake_readiness import build_report

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "ebeaa2884bce22e891d15da7c1f61962dde0699a"
SOURCE_REPO = "https://github.com/pilialvu75-hue/Mia"
LICENSE_BLOB = "551bc9050a44181342ec8a7c8543af1c90fd0992"
IDS = (
    "release.packaging.firstparty.mia",
    "release.update_manager.firstparty.mia",
    "voice.stt.firstparty.mia",
    "voice.tts.firstparty.mia",
)


class PinnedMiaLicenseTests(unittest.TestCase):
    def test_license_bytes_match_mia_immutable_source_commit(self):
        for asset_id in IDS:
            with self.subTest(asset=asset_id):
                folder = ROOT / "intake" / asset_id / "0.1.0"
                manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
                provenance = manifest["provenance"]
                self.assertEqual(provenance["source_repository"], SOURCE_REPO)
                self.assertEqual(provenance["source_commit"], SOURCE_COMMIT)
                self.assertEqual(manifest["payload"]["upstream_commit"], SOURCE_COMMIT)
                self.assertEqual(manifest["payload"]["upstream_repository"], SOURCE_REPO)
                self.assertEqual(provenance["license"], "MIT")
                self.assertEqual(provenance["license_file"], "provenance/LICENSE")
                data = (folder / provenance["license_file"]).read_bytes()
                self.assertEqual(hashlib.sha1(
                    b"blob " + str(len(data)).encode("ascii") + b"\\0" + data
                ).hexdigest(), LICENSE_BLOB)
                self.assertIn(b"Copyright (c) 2026 Mia contributors", data)
                self.assertEqual(manifest["status"], "discovered")
                self.assertIs(manifest["validation"]["tests_passed"], False)
                self.assertIs(manifest["security"]["reviewed"], False)

    def test_readiness_reduces_license_gap_but_never_certifies_mia_sources(self):
        report = build_report(ROOT)
        candidates = {x["asset_id"]: x for x in report["candidates"]}
        for asset_id in IDS:
            with self.subTest(asset=asset_id):
                record = candidates[asset_id]
                self.assertNotIn("LICENSE_EVIDENCE_MISSING", record["blockers"])
                self.assertIn("SOURCE_SNAPSHOT_MISSING", record["blockers"])
                self.assertIn("REPRODUCIBLE_TEST_EVIDENCE_MISSING", record["blockers"])
                self.assertIn("SECURITY_REVIEW_EVIDENCE_MISSING", record["blockers"])
                self.assertIs(record["independent_certification_authorized"], False)
        self.assertEqual(report["summary"]["ready_for_automatic_certification"], 0)


if __name__ == "__main__":
    unittest.main()
