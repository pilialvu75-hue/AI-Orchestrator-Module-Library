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

    def test_every_qualified_package_is_resolvable(self):
        index = json.loads((ROOT / "packages/development-index.json").read_text())
        entries = index["packages"]
        self.assertGreaterEqual(len(entries), 15)
        for entry in entries:
            package = json.loads((ROOT / entry["path"]).read_text())["package"]
            for target in entry["validated_targets"]:
                for capability in package["capabilities"]:
                    for contract in package["contracts"]:
                        with self.subTest(pin=entry["pin"], target=target, contract=contract):
                            found = query(ROOT, capability, contract, target)
                            matching = [r for r in found if r["pin"] == entry["pin"]]
                            self.assertEqual(len(matching), 1)
                            self.assertEqual(matching[0]["package_sha256"], entry["package_sha256"])
                            self.assertFalse(matching[0]["production_approved"])

    def test_desktop_evidence_resolves_all_recorded_pins(self):
        ledger = json.loads((ROOT / "packages/development-platform-evidence.json").read_text())
        index = json.loads((ROOT / "packages/development-index.json").read_text())
        entries = {e["pin"]: e for e in index["packages"]}
        for row in ledger["records"]:
            entry = entries.get(row["pin"])
            if not entry or entry["package_sha256"] != row["package_sha256"]:
                continue
            package = json.loads((ROOT / entry["path"]).read_text())["package"]
            for cap in package["capabilities"]:
                for contract in package["contracts"]:
                    found = query(ROOT, cap, contract, row["target"])
                    self.assertTrue(any(x["pin"] == row["pin"] for x in found))

    def test_stale_platform_evidence_cannot_authorize(self):
        cap = "utility.llm_generated.adjacent_pairs"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "packages", root / "packages")
            path = root / "packages/development-platform-evidence.json"
            ledger = json.loads(path.read_text())
            for row in ledger["records"]:
                if row["target"] == "windows":
                    row["package_sha256"] = "0" * 64
            path.write_text(json.dumps(ledger))
            self.assertEqual(query(root, cap, cap + ".v1", "windows"), [])
            self.assertTrue(query(root, cap, cap + ".v1", "linux"))
