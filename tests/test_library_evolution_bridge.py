from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from library_evolution_bridge import EvolutionBridgeError, REQUIRED_GATES, stage_evolution_work


def _request() -> dict:
    return {
        "schema_version": 1,
        "request_type": "library_module_improvement",
        "proposal_id": "proposal-123",
        "capability_id": "ai.acceleration_backend",
        "objective": "Implement only the useful capability delta.",
        "knowledge_delta": ["practice:ci_present", "topic:vulkan"],
        "acceptance_gates": list(REQUIRED_GATES),
        "mutation_policy": "isolated_candidate_no_library_mutation",
    }


class LibraryEvolutionBridgeTest(unittest.TestCase):
    def test_stages_sanitized_work_with_library_return_contract(self) -> None:
        staged = stage_evolution_work(_request())
        self.assertEqual(staged.payload["state"], "staged")
        self.assertEqual(staged.payload["proposal_id"], "proposal-123")
        self.assertEqual(
            staged.payload["required_output"],
            {
                "type": "library_intake_bundle",
                "status": "discovered",
                "path_scope": "intake/<asset>/<version>",
            },
        )

    def test_work_identity_is_deterministic(self) -> None:
        first = stage_evolution_work(_request())
        second = stage_evolution_work(_request())
        self.assertEqual(first.work_id, second.work_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())

    def test_rejects_executable_or_source_payload(self) -> None:
        for field in ("source", "source_code", "files", "payload", "patch", "diff", "commands"):
            with self.subTest(field=field):
                request = _request()
                request[field] = "forbidden"
                with self.assertRaisesRegex(EvolutionBridgeError, "forbidden"):
                    stage_evolution_work(request)

    def test_rejects_weakened_acceptance_gates(self) -> None:
        request = _request()
        request["acceptance_gates"] = ["implementation_tests_pass"]
        with self.assertRaisesRegex(EvolutionBridgeError, "acceptance gates"):
            stage_evolution_work(request)

    def test_rejects_direct_library_mutation_policy(self) -> None:
        request = _request()
        request["mutation_policy"] = "write_modules_directly"
        with self.assertRaisesRegex(EvolutionBridgeError, "mutation_policy"):
            stage_evolution_work(request)


if __name__ == "__main__":
    unittest.main()
