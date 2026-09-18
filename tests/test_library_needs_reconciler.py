from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from library_needs_reconciler import reconcile  # noqa: E402


class NeedsReconcilerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "catalog").mkdir()
    def tearDown(self): self.temp.cleanup()
    def write(self, name, value):
        (self.root / "catalog" / name).write_text(json.dumps(value), encoding="utf-8")
    def test_merges_extension_and_marks_only_fully_covered_need_satisfied(self):
        self.write("needs.json", {"schema_version":1,"updated_at":"x","items":[
            {"capability_id":"a.cap","title":"A","priority":"high","desired_candidates":1,"status":"needed","targets":["linux"]}
        ]})
        self.write("needs.platform-extension.json", {"schema_version":1,"updated_at":"x","items":[
            {"capability_id":"b.cap","title":"B","priority":"medium","desired_candidates":1,"status":"needed","targets":["linux","windows"]}
        ]})
        self.write("index.json", {"assets":[
            {"id":"a","status":"certified","capabilities":["a.cap"],"platforms":["linux"]},
            {"id":"b","status":"certified","capabilities":["b.cap"],"platforms":["linux"]}
        ]})
        report = reconcile(self.root, now="2026-09-18T00:00:00Z")
        data=json.loads((self.root/"catalog"/"needs.json").read_text())
        rows={x["capability_id"]:x for x in data["items"]}
        self.assertEqual("satisfied", rows["a.cap"]["status"])
        self.assertEqual("needed", rows["b.cap"]["status"])
        self.assertEqual(2, report["needs"])
    def test_revoked_asset_does_not_satisfy_need(self):
        self.write("needs.json", {"schema_version":1,"updated_at":"x","items":[
            {"capability_id":"a.cap","title":"A","priority":"high","desired_candidates":1,"status":"satisfied","targets":["linux"]}
        ]})
        self.write("index.json", {"assets":[
            {"id":"a","status":"certified","availability":"revoked","capabilities":["a.cap"],"platforms":["linux"]}
        ]})
        reconcile(self.root, now="2026-09-18T00:00:00Z")
        data=json.loads((self.root/"catalog"/"needs.json").read_text())
        self.assertEqual("needed", data["items"][0]["status"])

if __name__ == "__main__":
    unittest.main()
