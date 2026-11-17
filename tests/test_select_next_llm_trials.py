"""Regressions for the automatic, no-manual-intervention Qwen backlog."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from select_next_llm_trials import remaining, select, verify_selected


def spec(i):
    return {
        "id": f"example_{i}",
        "package_name": f"aivexus_example_{i}",
        "library_path": f"lib/example_{i}.dart",
        "instruction": "Original pure Dart function returns a new list",
        "consumer_source": "void main() { print('PASS'); }",
    }


class AutomatedBacklogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "examples").mkdir()
        self.specs = [spec(i) for i in range(5)]
        (self.root / "examples/real-llm-module-trials.json").write_text(
            json.dumps({"schema": "aivexus.module-llm-trials.v1",
                        "policy": "ISOLATED_NONCERTIFIED_NO_AUTOMATIC_RELEASE",
                        "trials": self.specs}), encoding="utf-8")
        self.selected = self.root / "selected.json"

    def persist(self, chosen):
        self.selected.write_text(json.dumps(chosen), encoding="utf-8")

    def test_fresh_two_then_skip_both_without_changing_registry(self):
        one = select(self.root)
        self.assertEqual([s["id"] for s in one["trials"]],
                         ["example_0", "example_1"])
        self.persist(one)
        self.assertEqual(len(verify_selected(self.root, self.selected)), 2)
        for i in [0, 1]:
            path = self.root / f"intake/utility.llm_generated.example_{i}/0.1.0"
            path.mkdir(parents=True)
            (path / "manifest.json").write_text('{"status":"tested"}')
        self.assertEqual([s["id"] for s in select(self.root)["trials"]],
                         ["example_2", "example_3"])
        self.assertEqual(len(remaining(self.root)), 3)

    def test_schedule_round_robin_and_last_one(self):
        self.assertEqual([s["id"] for s in select(self.root, offset=2)["trials"]],
                         ["example_2", "example_3"])
        self.assertEqual([s["id"] for s in select(self.root, offset=4)["trials"]],
                         ["example_4", "example_0"])
        for i in range(4):
            (self.root / f"intake/utility.llm_generated.example_{i}/0.1.0").mkdir(parents=True)
        self.assertEqual([s["id"] for s in select(self.root, offset=25)["trials"]],
                         ["example_4"])
        (self.root / "modules/utility.llm_generated.example_4/0.1.0").mkdir(parents=True)
        self.assertEqual(select(self.root)["trials"], [])

    def test_untrusted_selected_source_or_consumer_is_rejected(self):
        packet = select(self.root)
        packet["trials"][0]["consumer_source"] = "forged untrusted approval"
        self.persist(packet)
        with self.assertRaisesRegex(ValueError, "differs from canonical"):
            verify_selected(self.root, self.selected)

    def test_duplicate_or_unregistered_modules_are_rejected(self):
        packet = select(self.root)
        packet["trials"].append(packet["trials"][0])
        self.persist(packet)
        with self.assertRaises(ValueError):
            verify_selected(self.root, self.selected)
        packet = select(self.root)
        packet["trials"][0]["id"] = "forged"
        self.persist(packet)
        with self.assertRaises(ValueError):
            verify_selected(self.root, self.selected)

    def test_invalid_offset_or_batch_does_not_fallback_to_first_module(self):
        for offset, size in ((-1, 2), (0, 0), (0, 3), (True, 2)):
            with self.subTest(offset=offset, batch=size):
                with self.assertRaises(ValueError):
                    select(self.root, offset=offset, batch_size=size)


if __name__ == "__main__":
    unittest.main()
