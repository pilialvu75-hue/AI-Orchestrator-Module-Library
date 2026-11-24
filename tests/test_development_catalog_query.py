import sys
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
