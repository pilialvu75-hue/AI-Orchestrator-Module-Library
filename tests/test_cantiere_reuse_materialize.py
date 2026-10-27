"""Source staging must preserve exact Cantiere bytes and never run them."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from cantiere_code_reuse_harvest import REPO, SCHEMA
from cantiere_reuse_materialize import MaterializationError, stage_one
from library_source_integrity import payload_tree_sha256

HEAD = "c" * 40
SOURCE = b"import pathlib\nclass Candidate:\n    pass\n"
TEST = b"import unittest\nclass CandidateTest(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"
NAME = "sandbox_candidate"
SOURCE_PATH = "tool/" + NAME + ".py"
TEST_PATH = "test/tool/test_" + NAME + ".py"


def observed(path, content, classification):
    return {
        "path": path, "classification": classification,
        "module_status": "not_materialized", "source_commit": HEAD,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "capability_hint": "library.integration",
    }


class CantiereMaterializationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        template = ROOT / "intake/library.integration.firstparty.cantiere_preview_reader/0.1.0/manifest.json"
        target = self.root / "intake/library.integration.firstparty.cantiere_preview_reader/0.1.0/manifest.json"
        target.parent.mkdir(parents=True)
        shutil.copyfile(template, target)
        self.ledger_file = self.root / "catalog/cantiere-code-reuse-ledger.json"
        self.ledger_file.parent.mkdir(parents=True)
        self.rows = [
            observed(SOURCE_PATH, SOURCE, "candidate_requires_extraction_and_tests"),
            observed(TEST_PATH, TEST, "test_support"),
        ]
        self.save_ledger()
        self.downloads = []

    def save_ledger(self):
        self.ledger_file.write_text(json.dumps({
            "schema": SCHEMA, "source_repository": REPO,
            "last_scanned_sha": HEAD, "observations": self.rows,
        }), encoding="utf-8")

    def raw_get(self, url):
        self.downloads.append(url)
        if url.endswith("/" + SOURCE_PATH):
            return SOURCE
        if url.endswith("/" + TEST_PATH):
            return TEST
        raise ValueError("unexpected network request")

    def test_stages_actual_test_backed_source_with_digest_and_pinned_commit(self):
        result = stage_one(self.root, raw_get=self.raw_get)
        self.assertEqual(result["staged"], 1)
        self.assertEqual(result["status"], "source_materialized_needs_tests")
        base = self.root / "intake" / result["library_pin"].replace("@", "/")
        manifest = json.loads((base / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "discovered")
        self.assertIs(manifest["validation"]["tests_passed"], False)
        self.assertIs(manifest["security"]["reviewed"], False)
        self.assertEqual(manifest["provenance"]["source_commit"], HEAD)
        self.assertEqual(manifest["payload"]["sha256"],
                         payload_tree_sha256(base / "payload/src"))
        self.assertEqual((base / "payload/src" / SOURCE_PATH).read_bytes(), SOURCE)
        self.assertEqual((base / "payload/src" / TEST_PATH).read_bytes(), TEST)
        self.assertTrue(all(HEAD in url for url in self.downloads))
        state = json.loads(self.ledger_file.read_text())
        self.assertEqual(state["observations"][0]["library_pin"],
                         result["library_pin"])
        self.assertEqual(stage_one(self.root, raw_get=self.raw_get)["staged"], 0)

    def test_missing_matching_test_never_stages(self):
        self.rows.pop()
        self.save_ledger()
        self.assertEqual(stage_one(self.root, raw_get=self.raw_get)["staged"], 0)
        self.assertEqual(self.downloads, [])

    def test_tampering_preserves_original_ledger_and_does_not_stage(self):
        before = self.ledger_file.read_bytes()
        self.rows[1]["source_sha256"] = "0" * 64
        self.save_ledger()
        before = self.ledger_file.read_bytes()
        with self.assertRaisesRegex(MaterializationError, "source hash mismatch"):
            stage_one(self.root, raw_get=self.raw_get)
        self.assertEqual(self.ledger_file.read_bytes(), before)
        self.assertFalse((self.root / ("intake/library.integration.firstparty.cantiere_" + NAME)).exists())

    def test_untrusted_source_is_never_imported_or_executed_in_stager(self):
        malicious = b"from pathlib import Path\nPath('EXECUTED').write_text('unsafe')\n"
        self.rows[0]["source_sha256"] = hashlib.sha256(malicious).hexdigest()
        self.save_ledger()
        def get(url):
            if url.endswith("/" + SOURCE_PATH):
                return malicious
            return TEST
        self.assertEqual(stage_one(self.root, raw_get=get)["staged"], 1)
        self.assertFalse((self.root / "EXECUTED").exists())

    def test_existing_materialized_candidate_is_never_overwritten(self):
        self.assertEqual(stage_one(self.root, raw_get=self.raw_get)["staged"], 1)
        first = self.ledger_file.read_text()
        self.assertEqual(stage_one(self.root, raw_get=self.raw_get)["staged"], 0)
        self.assertEqual(self.ledger_file.read_text(), first)


if __name__ == "__main__":
    unittest.main()
