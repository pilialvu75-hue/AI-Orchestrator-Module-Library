from __future__ import annotations

import sys
from pathlib import Path

import pytest

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


def test_stages_sanitized_work_with_library_return_contract() -> None:
    staged = stage_evolution_work(_request())
    assert staged.payload["state"] == "staged"
    assert staged.payload["proposal_id"] == "proposal-123"
    assert staged.payload["required_output"] == {
        "type": "library_intake_bundle",
        "status": "discovered",
        "path_scope": "intake/<asset>/<version>",
    }


def test_work_identity_is_deterministic() -> None:
    first = stage_evolution_work(_request())
    second = stage_evolution_work(_request())
    assert first.work_id == second.work_id
    assert first.canonical_json() == second.canonical_json()


@pytest.mark.parametrize("field", ["source", "source_code", "files", "payload", "patch", "diff", "commands"])
def test_rejects_executable_or_source_payload(field: str) -> None:
    request = _request()
    request[field] = "forbidden"
    with pytest.raises(EvolutionBridgeError, match="forbidden"):
        stage_evolution_work(request)


def test_rejects_weakened_acceptance_gates() -> None:
    request = _request()
    request["acceptance_gates"] = ["implementation_tests_pass"]
    with pytest.raises(EvolutionBridgeError, match="acceptance gates"):
        stage_evolution_work(request)


def test_rejects_direct_library_mutation_policy() -> None:
    request = _request()
    request["mutation_policy"] = "write_modules_directly"
    with pytest.raises(EvolutionBridgeError, match="mutation_policy"):
        stage_evolution_work(request)
