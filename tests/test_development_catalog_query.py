import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from development_catalog_query import query

class DevelopmentCatalogTests(unittest.TestCase):
    def test_real_package(self):
        cap = "utility.llm_generated.adjacent_pairs"
        found = query(ROOT, cap, cap + ".v1", "linux")
        self.assertTrue(found)
        self.assertFalse(found[0]["production_approved"])

    def test_unverified_target(self):
        cap = "utility.llm_generated.adjacent_pairs"
        self.assertEqual(query(ROOT, cap, cap + ".v1", "android"), [])

    def test_wrong_contract(self):
        self.assertEqual(query(ROOT, "utility.llm_generated.adjacent_pairs", "wrong", "linux"), [])

    def test_tampered_payload_rejected(self):
        cap = "utility.llm_generated.adjacent_pairs"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = json.loads((ROOT / "packages/development-index.json").read_text())
            entry = next(e for e in index["packages"] if e["pin"].startswith(cap + "@"))
            index["packages"] = [entry]
            (root / "packages").mkdir()
            (root / "packages/development-index.json").write_text(json.dumps(index))
            path = root / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / entry["path"], path)
            envelope = json.loads(path.read_text())
            envelope["package"]["files"][0]["content"] = "tampered"
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                query(root, cap, cap + ".v1", "linux")
