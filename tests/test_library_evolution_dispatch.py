from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from library_evolution_bridge import REQUIRED_GATES, stage_evolution_work
from library_evolution_dispatch import EvolutionDispatchError, claim, prepare_claim
from library_evolution_queue import EvolutionWorkQueue


def _stage(root: Path):
    work = stage_evolution_work({
        "request_type": "library_module_improvement",
        "proposal_id": "proposal-dispatch-1",
        "capability_id": "ai.acceleration_backend",
        "objective": "Adapt only the useful capability delta.",
        "knowledge_delta": ["practice:readme_present"],
        "acceptance_gates": list(REQUIRED_GATES),
        "mutation_policy": "isolated_candidate_no_library_mutation",
    })
    EvolutionWorkQueue(root).stage(work)
    return work


class EvolutionDispatchTest(unittest.TestCase):
    def test_prepare_is_read_only_and_library_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = _stage(root)
            envelope = prepare_claim(root, work.work_id)
            self.assertEqual(envelope["source"], "library_evolution_queue")
            self.assertEqual(envelope["work_id"], work.work_id)
            self.assertEqual(EvolutionWorkQueue(root).load(work.work_id)["state"], "staged")

    def test_claim_transitions_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = _stage(root)
            result = claim(root, work.work_id)
            self.assertEqual(result["transition"]["state"], "claimed")
            self.assertEqual(EvolutionWorkQueue(root).load(work.work_id)["state"], "claimed")
            with self.assertRaisesRegex(EvolutionDispatchError, "only staged"):
                claim(root, work.work_id)

    def test_nonexistent_work_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(EvolutionDispatchError, "unknown"):
                prepare_claim(Path(tmp), "evo-" + "0" * 24)


if __name__ == "__main__":
    unittest.main()
