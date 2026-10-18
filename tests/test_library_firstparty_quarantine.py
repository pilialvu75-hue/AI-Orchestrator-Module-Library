"""First-party intake may auto-quarantine, never auto-test or certify."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.library_firstparty_quarantine import ALLOWED, triage

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"


class FirstPartyQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for asset_id in ALLOWED:
            source = ROOT / "intake" / asset_id / VERSION / "manifest.json"
            target = self.root / "intake" / asset_id / VERSION / "manifest.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def file(self, asset_id):
        return self.root / "intake" / asset_id / VERSION / "manifest.json"

    def test_two_existing_candidates_advance_to_quarantine_only(self):
        report = triage(root=self.root, apply=True)
        self.assertEqual(report["certified_count_added"], 0)
        self.assertEqual(len(report["items"]), 2)
        for entry in report["items"]:
            self.assertEqual(entry["result"], "QUARANTINED")
            self.assertEqual(entry["status"], "quarantined")
            self.assertFalse(entry["certified"])
            self.assertEqual(set(entry["blockers"]), {
                "LICENSE_EVIDENCE_MISSING", "LOCAL_HASHED_PAYLOAD_MISSING",
                "REPRODUCIBLE_TEST_EVIDENCE_MISSING",
                "SECURITY_REVIEW_EVIDENCE_MISSING",
            })
            manifest = json.loads(self.file(entry["asset_id"]).read_text())
            self.assertEqual(manifest["status"], "quarantined")
            self.assertEqual(manifest["provenance"]["license"], "NOASSERTION")
            self.assertIsNone(manifest["payload"]["path"])
            self.assertFalse(manifest["validation"]["tests_passed"])
            self.assertFalse(manifest["security"]["reviewed"])

    def test_dry_run_never_writes_any_manifest(self):
        before = {asset: self.file(asset).read_bytes() for asset in ALLOWED}
        result = triage(root=self.root, apply=False)
        self.assertTrue(result["read_only"])
        self.assertTrue(all(x["result"] == "ELIGIBLE_FOR_QUARANTINE"
                            for x in result["items"]))
        self.assertEqual(before, {asset: self.file(asset).read_bytes()
                                  for asset in ALLOWED})

    def test_repeated_run_is_idempotent(self):
        triage(root=self.root, apply=True)
        before = {asset: self.file(asset).read_bytes() for asset in ALLOWED}
        result = triage(root=self.root, apply=True)
        self.assertTrue(all(x["result"] == "NO_MUTATION" for x in result["items"]))
        self.assertEqual(before, {asset: self.file(asset).read_bytes()
                                  for asset in ALLOWED})

    def test_source_commit_and_origin_are_not_worker_controlled(self):
        for change in (
            lambda m: m["provenance"].update(source_repository="https://attacker.example/repo"),
            lambda m: m["payload"].update(upstream_commit="f" * 40),
            lambda m: m.update(id="other.asset"),
            lambda m: m["provenance"].update(license="MIT", origin="imported"),
            lambda m: m.update(status="certified"),
        ):
            with self.subTest(change=str(change)):
                path = self.file(ALLOWED[0])
                original = json.loads((ROOT / "intake" / ALLOWED[0] / VERSION / "manifest.json").read_text())
                change(original)
                path.write_text(json.dumps(original))
                with self.assertRaisesRegex(ValueError, "unrecognized"):
                    triage(root=self.root, apply=True)

    def test_absent_candidate_is_reported_not_fabricated(self):
        self.file(ALLOWED[1]).unlink()
        result = triage(root=self.root, apply=False)
        self.assertEqual(result["items"][1]["result"], "NOT_IN_INTAKE")
        self.assertFalse(self.file(ALLOWED[1]).exists())

    def test_symlinked_manifest_is_rejected_without_external_execution(self):
        target = self.file(ALLOWED[0])
        data = target.read_bytes()
        target.unlink()
        outside = self.root / "untrusted.json"
        outside.write_bytes(data)
        target.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            triage(root=self.root, apply=True)


if __name__ == "__main__":
    unittest.main()
