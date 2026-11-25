import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from needs_research_plan import plan

class ResearchPlanTests(unittest.TestCase):
    def test_current_catalog(self):
        needs = json.loads((ROOT / "catalog/needs.json").read_text())
        expected = {n["capability_id"] for n in needs["items"] if n["status"] == "needed"}
        rows = plan(ROOT)["items"]
        self.assertEqual({r["capability_id"] for r in rows}, expected)
        self.assertTrue(all(r["desired_candidates"] == 2 for r in rows))

    def test_new_need_without_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog").mkdir()
            row = dict(capability_id="example.new", title="New", priority="high",
                       targets=["linux"], desired_candidates=2, status="needed")
            (root / "catalog/needs.json").write_text(json.dumps({"items":[row]}))
            self.assertEqual(plan(root)["items"][0]["capability_id"], "example.new")
            row["status"] = "closed"
            (root / "catalog/needs.json").write_text(json.dumps({"items":[row]}))
            self.assertEqual(plan(root)["items"], [])
