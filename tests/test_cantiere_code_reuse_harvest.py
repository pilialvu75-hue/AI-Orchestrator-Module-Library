"""Cantiere->Library harvesting observes source without certifying anything."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from cantiere_code_reuse_harvest import (
    HarvestError, REPO, SCHEMA, analyse_code, run,
)

BASE = "a" * 40
HEAD = "b" * 40


class HarvestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "catalog/cantiere-code-reuse-ledger.json"
        self.events = []
        self.files = [
            {"filename": "lib/app_factory/workshop/reusable.dart",
             "status": "modified", "sha": "c" * 40},
            {"filename": "test/app_factory/workshop/reusable_test.dart",
             "status": "added", "sha": "d" * 40},
            {"filename": "assets/logo.png", "status": "modified"},
            {"filename": "lib/retired.dart", "status": "removed"},
        ]

    def api(self, url):
        self.events.append(url)
        if url.endswith("/commits/main"):
            return {"sha": HEAD, "parents": [{"sha": BASE}]}
        return {"status": "ahead", "ahead_by": 1, "files": self.files}

    def raw(self, url):
        self.events.append(url)
        if "/test/" in url:
            return b"void main() { assert(true); }\n"
        return b"class ReusableHelper { const ReusableHelper(); }\n"

    def test_all_modified_code_is_recorded_not_mistaken_for_a_module(self):
        report = run(self.root, api_get=self.api, raw_get=self.raw)
        self.assertEqual(report["new_code_files"], 3)
        self.assertEqual(report["new_candidates"], 1)
        state = json.loads(self.path.read_text())
        self.assertEqual(state["last_scanned_sha"], HEAD)
        self.assertEqual(len(state["observations"]), 3)
        by_path = {x["path"]: x for x in state["observations"]}
        self.assertEqual(by_path["lib/app_factory/workshop/reusable.dart"]["classification"],
                         "candidate_requires_extraction_and_tests")
        self.assertEqual(by_path["test/app_factory/workshop/reusable_test.dart"]["classification"],
                         "test_support")
        self.assertEqual(by_path["lib/retired.dart"]["classification"],
                         "removed_source")
        self.assertTrue(all(x["module_status"] == "not_materialized"
                            for x in state["observations"]))
        self.assertTrue(all("b" * 40 in url for url in self.events
                            if "raw.githubusercontent.com" in url))

    def test_same_head_does_not_duplicate_or_refetch_code(self):
        run(self.root, api_get=self.api, raw_get=self.raw)
        self.events.clear()
        second = run(self.root, api_get=self.api, raw_get=self.raw)
        self.assertEqual(second["result"], "unchanged")
        self.assertEqual(len(self.events), 1)
        self.assertEqual(len(json.loads(self.path.read_text())["observations"]), 3)

    def test_overfull_compare_keeps_last_cursor_unchanged(self):
        self.files = [{"filename": f"lib/m{i}.dart", "status": "modified"}
                      for i in range(101)]
        with self.assertRaisesRegex(HarvestError, "too many modified source"):
            run(self.root, api_get=self.api, raw_get=self.raw)
        self.assertFalse(self.path.exists())

    def test_bad_raw_data_keeps_last_cursor_unchanged(self):
        def error_raw(url):
            raise HarvestError("source unavailable")
        with self.assertRaisesRegex(HarvestError, "source unavailable"):
            run(self.root, api_get=self.api, raw_get=error_raw)
        self.assertFalse(self.path.exists())

    def test_no_source_is_certified_by_static_analysis(self):
        result = analyse_code(path="lib/core/update_helper.dart",
                              content=b"class UpdateHelper {}\n",
                              commit=HEAD, blob_sha="c" * 40)
        self.assertEqual(result["capability_hint"], "release.update_manager")
        self.assertEqual(result["module_status"], "not_materialized")
        self.assertIs(result["tested"], False)
        self.assertIs(result["certified"], False)


if __name__ == "__main__":
    unittest.main()
