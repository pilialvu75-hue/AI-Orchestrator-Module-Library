from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from library_evolution_bridge import REQUIRED_GATES, stage_evolution_work
from library_evolution_queue import EvolutionQueueError, EvolutionWorkQueue


def _work():
    return stage_evolution_work({
        "request_type": "library_module_improvement",
        "proposal_id": "proposal-queue-1",
        "capability_id": "ai.acceleration_backend",
        "objective": "Adapt the useful capability delta in an isolated Cantiere workspace.",
        "knowledge_delta": ["practice:ci_present"],
        "acceptance_gates": list(REQUIRED_GATES),
        "mutation_policy": "isolated_candidate_no_library_mutation",
    })


class EvolutionWorkQueueTest(unittest.TestCase):
    def test_stage_is_durable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = EvolutionWorkQueue(Path(tmp))
            work = _work()
            self.assertEqual(queue.stage(work)["result"], "staged")
            self.assertEqual(queue.stage(work)["result"], "already_staged")
            reopened = EvolutionWorkQueue(Path(tmp))
            self.assertEqual(reopened.load(work.work_id)["state"], "staged")

    def test_claim_and_return_require_order_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = EvolutionWorkQueue(Path(tmp))
            work = _work()
            queue.stage(work)
            self.assertEqual(queue.transition(work.work_id, "claimed")["state"], "claimed")
            with self.assertRaisesRegex(EvolutionQueueError, "requires receipt"):
                queue.transition(work.work_id, "returned")
            receipt = {"bundle_sha256": "a" * 64, "result": "library_intake_bundle"}
            self.assertEqual(queue.transition(work.work_id, "returned", receipt=receipt)["state"], "returned")
            self.assertEqual(queue.transition(work.work_id, "returned", receipt=receipt)["result"], "already_transitioned")

    def test_cannot_skip_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = EvolutionWorkQueue(Path(tmp))
            work = _work()
            queue.stage(work)
            with self.assertRaisesRegex(EvolutionQueueError, "invalid transition"):
                queue.transition(work.work_id, "returned", receipt={"result": "forged"})

    def test_divergent_same_identity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = EvolutionWorkQueue(Path(tmp))
            work = _work()
            queue.stage(work)
            altered = stage_evolution_work({
                "request_type": "library_module_improvement",
                "proposal_id": "proposal-queue-1",
                "capability_id": "ai.acceleration_backend",
                "objective": "Different objective.",
                "knowledge_delta": ["practice:different"],
                "acceptance_gates": list(REQUIRED_GATES),
                "mutation_policy": "isolated_candidate_no_library_mutation",
            })
            self.assertEqual(work.work_id, altered.work_id)
            with self.assertRaisesRegex(EvolutionQueueError, "divergent"):
                queue.stage(altered)


if __name__ == "__main__":
    unittest.main()
