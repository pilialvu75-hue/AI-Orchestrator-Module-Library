from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from library_evolution_bridge import REQUIRED_GATES, stage_evolution_work
from library_evolution_dispatch import EvolutionDispatchError
from library_evolution_legacy_reconcile import preview_legacy_reconciliation
from library_evolution_queue import EvolutionWorkQueue


class LegacyReconciliationPreviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = EvolutionWorkQueue(self.root)
        self.work = stage_evolution_work({
            "request_type": "library_module_improvement",
            "proposal_id": "legacy-proposal",
            "capability_id": "ai.acceleration_backend",
            "objective": "Isolated capability improvement",
            "knowledge_delta": ["practice:readme_present"],
            "acceptance_gates": list(REQUIRED_GATES),
            "mutation_policy": "isolated_candidate_no_library_mutation",
        })
        self.queue.stage(self.work)
        self.historical = copy.deepcopy(self.queue.load(self.work.work_id))
        legacy = copy.deepcopy(self.historical)
        legacy["state"] = "claimed"
        self.queue._write(legacy)

    def test_preview_is_read_only_and_repeatable(self) -> None:
        before = self.queue.load(self.work.work_id)
        first = preview_legacy_reconciliation(self.root, self.work.work_id, self.historical)
        second = preview_legacy_reconciliation(self.root, self.work.work_id, self.historical)
        self.assertEqual(first, second)
        self.assertEqual(first["action"], "REVIEW_REQUIRED")
        self.assertFalse(first["queue_mutated"])
        self.assertEqual(before, self.queue.load(self.work.work_id))

    def test_rejects_modified_current_claim(self) -> None:
        modified = self.queue.load(self.work.work_id)
        modified["objective"] = "Tampered"
        self.queue._write(modified)
        with self.assertRaisesRegex(EvolutionDispatchError, "differs"):
            preview_legacy_reconciliation(self.root, self.work.work_id, self.historical)

    def test_rejects_wrong_historical_state(self) -> None:
        staged = copy.deepcopy(self.historical)
        staged["state"] = "claimed"
        with self.assertRaisesRegex(EvolutionDispatchError, "historical staged"):
            preview_legacy_reconciliation(self.root, self.work.work_id, staged)

    def test_rejects_unclaimed_current(self) -> None:
        current = self.queue.load(self.work.work_id)
        current["state"] = "staged"
        self.queue._write(current)
        with self.assertRaisesRegex(EvolutionDispatchError, "requires claimed"):
            preview_legacy_reconciliation(self.root, self.work.work_id, self.historical)


if __name__ == "__main__":
    unittest.main()
