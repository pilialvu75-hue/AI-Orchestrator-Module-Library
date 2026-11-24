import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from reconcile_platform_evidence import reconcile, TARGETS

class PlatformEvidenceTests(unittest.TestCase):
    def setUp(self):
        index = json.loads((ROOT / "packages/development-index.json").read_text())
        self.items = [dict(pin=r["pin"], package_sha256=r["package_sha256"],
                           independent_dart_consumer="PASS",
                           source="published Library experimental export",
                           production_approved=False, certified=False)
                      for r in index["packages"]]
        self.receipts = {t: dict(schema="aivexus.llm-published-consumer.v1",
                                complete=True, certified=False,
                                items=[dict(i) for i in self.items]) for t in TARGETS}
        self.jobs = dict(zip(TARGETS, (1, 2, 3)))

    def test_repeat_is_idempotent(self):
        actual = reconcile(ROOT, self.receipts, 123, self.jobs)
        expected = json.loads((ROOT / "packages/development-platform-evidence.json").read_text())
        self.assertEqual(actual, expected)

    def test_missing_platform(self):
        del self.receipts["windows"]
        with self.assertRaises(ValueError):
            reconcile(ROOT, self.receipts, 123, self.jobs)

    def test_failed_consumer(self):
        self.receipts["windows"]["items"][0]["independent_dart_consumer"] = "FAIL"
        with self.assertRaises(ValueError):
            reconcile(ROOT, self.receipts, 123, self.jobs)

    def test_wrong_digest(self):
        self.receipts["macos"]["items"][0]["package_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            reconcile(ROOT, self.receipts, 123, self.jobs)

    def test_incomplete_coverage(self):
        self.receipts["macos"]["items"].pop()
        with self.assertRaises(ValueError):
            reconcile(ROOT, self.receipts, 123, self.jobs)

    def test_duplicate(self):
        self.receipts["linux"]["items"].append(self.items[0])
        with self.assertRaises(ValueError):
            reconcile(ROOT, self.receipts, 123, self.jobs)


    def test_missing_evidence_is_recovered(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__", ".dart_tool", ".venv"))
            path = root / "packages/development-platform-evidence.json"
            prior = json.loads(path.read_text())
            missing = prior["records"].pop()
            path.write_text(json.dumps(prior))
            actual = reconcile(root, self.receipts, 123, self.jobs)
            self.assertEqual(len(actual["records"]), len(prior["records"]) + 1)
            recovered = next(r for r in actual["records"]
                             if r["pin"] == missing["pin"] and r["target"] == missing["target"])
            self.assertEqual(recovered["package_sha256"], missing["package_sha256"])
            self.assertEqual(recovered["run_id"], 123)
            self.assertEqual(recovered["job_id"], self.jobs[missing["target"]])
