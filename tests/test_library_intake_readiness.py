"""The Library readiness snapshot is read-only and never implies certification."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.library_intake_readiness import ReadinessError, build_report

ROOT = Path(__file__).resolve().parents[1]
ID = "ai.model_storage.firstparty.sample"
VERSION = "0.1.0"


class LibraryReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "catalog").mkdir(parents=True)
        (self.root / "intake").mkdir()
        shutil.copy2(ROOT / "catalog/needs.json", self.root / "catalog/needs.json")
        shutil.copy2(ROOT / "catalog/index.json", self.root / "catalog/index.json")
        source = ROOT / "intake/ai.model_storage.firstparty.ai-orchestrator-core/0.1.0/manifest.json"
        self.manifest = json.loads(source.read_text())
        self.manifest["id"] = ID
        self.base = self.root / "intake" / ID / VERSION
        self.base.mkdir(parents=True)
        self.save()

    def save(self):
        (self.base / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8",
        )

    def test_real_repository_counts_are_derived_and_no_candidate_is_certified(self):
        inventory = build_report(ROOT)
        self.assertEqual(inventory["report_type"], "read_only_evidence_gaps_not_certification")
        self.assertEqual(inventory["summary"]["certified_catalog_entries"],
                         len(json.loads((ROOT / "catalog/index.json").read_text())["assets"]))
        self.assertEqual(inventory["summary"]["intake_candidates"],
                         len(list((ROOT / "intake").glob("*/*/manifest.json"))))
        self.assertEqual(inventory["summary"]["ready_for_automatic_certification"], 0)
        self.assertTrue(all(not asset["independent_certification_authorized"]
                            for asset in inventory["candidates"]))
        self.assertEqual(inventory, build_report(ROOT))

    def test_unverified_manifest_remains_blocked_with_explicit_actions(self):
        inventory = build_report(self.root)
        candidate = inventory["candidates"][0]
        self.assertEqual(candidate["asset_id"], ID)
        self.assertEqual(candidate["status"], "discovered")
        self.assertEqual(set(candidate["blockers"]), {
            "LICENSE_EVIDENCE_MISSING",
            "SOURCE_SNAPSHOT_MISSING",
            "REPRODUCIBLE_TEST_EVIDENCE_MISSING",
            "SECURITY_REVIEW_EVIDENCE_MISSING",
        })
        self.assertEqual(len(candidate["next_actions"]), 4)
        self.assertFalse(candidate["independent_certification_authorized"])
        self.assertEqual(inventory["summary"]["blocked_intake_candidates"], 1)

    def test_coverage_tracks_certified_assets_separately_from_discovered_candidates(self):
        coverage = {x["capability_id"]: x for x in build_report(self.root)["coverage"]}
        storage = coverage["ai.model_storage"]
        self.assertEqual(storage["intake_candidates"], 1)
        self.assertEqual(storage["blocked_candidates"], 1)
        self.assertEqual(storage["certified_count"], 1)
        per_target = {x["target"]: x["certified_count"]
                      for x in storage["certified_by_target"]}
        self.assertEqual(per_target["web"], 0)
        self.assertGreaterEqual(per_target["linux"], 1)
        self.assertGreater(storage["remaining_to_goal"], 0)

    def test_self_reported_pass_does_not_confer_authorization(self):
        self.manifest["validation"]["tests_passed"] = True
        self.manifest["validation"]["test_report"] = "reports/test.json"
        self.manifest["validation"]["validated_on"] = ["android"]
        self.manifest["security"]["reviewed"] = True
        self.manifest["security"]["review_report"] = "reports/security.json"
        self.manifest["security"]["sbom"] = "reports/sbom.json"
        reports = self.base / "reports"
        reports.mkdir()
        for name in ("test.json", "security.json", "sbom.json"):
            (reports / name).write_text('{"asserted":true}')
        self.save()
        asset = build_report(self.root)["candidates"][0]
        self.assertNotIn("REPRODUCIBLE_TEST_EVIDENCE_MISSING", asset["blockers"])
        self.assertNotIn("SECURITY_REVIEW_EVIDENCE_MISSING", asset["blockers"])
        self.assertFalse(asset["independent_certification_authorized"])

    def test_restricted_license_requires_explicit_review_even_with_license_file(self):
        self.manifest["provenance"]["license"] = "AGPL-3.0"
        self.manifest["provenance"]["license_file"] = "LICENSE"
        (self.base / "LICENSE").write_text("license text")
        self.save()
        asset = build_report(self.root)["candidates"][0]
        self.assertIn("RESTRICTED_LICENSE_REVIEW_REQUIRED", asset["blockers"])
        self.assertNotIn("LICENSE_EVIDENCE_MISSING", asset["blockers"])
        self.assertFalse(asset["independent_certification_authorized"])

    def test_rejects_manifest_id_mismatch_and_missing_version(self):
        self.manifest["id"] = "wrong.asset"
        self.save()
        with self.assertRaisesRegex(ReadinessError, "identity"):
            build_report(self.root)
        self.manifest["id"] = ID
        self.manifest["status"] = "certified"
        self.save()
        with self.assertRaisesRegex(ReadinessError, "identity"):
            build_report(self.root)

    def test_rejects_symlink_manifest_and_source_snapshot(self):
        path = self.base / "manifest.json"
        path.unlink()
        outside = self.root / "outside.json"
        outside.write_text(json.dumps(self.manifest))
        path.symlink_to(outside)
        with self.assertRaisesRegex(ReadinessError, "symlink"):
            build_report(self.root)
        path.unlink()
        self.save()
        (self.base / "payload").symlink_to(self.root, target_is_directory=True)
        self.assertIn("SOURCE_SNAPSHOT_MISSING",
                      build_report(self.root)["candidates"][0]["blockers"])

    def test_untrusted_external_evidence_paths_do_not_escape_asset(self):
        self.manifest["provenance"]["license"] = "MIT"
        self.manifest["provenance"]["license_file"] = "../../catalog/index.json"
        self.manifest["validation"]["tests_passed"] = True
        self.manifest["validation"]["test_report"] = "../../catalog/index.json"
        self.save()
        asset = build_report(self.root)["candidates"][0]
        self.assertIn("LICENSE_EVIDENCE_MISSING", asset["blockers"])
        self.assertIn("REPRODUCIBLE_TEST_EVIDENCE_MISSING", asset["blockers"])

    def test_malformed_canonical_needs_fails_closed(self):
        path = self.root / "catalog/needs.json"
        data = json.loads(path.read_text())
        data["items"].append(copy.deepcopy(data["items"][0]))
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ReadinessError, "duplicate"):
            build_report(self.root)


if __name__ == "__main__":
    unittest.main()
