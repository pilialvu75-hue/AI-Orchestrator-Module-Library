from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA = "ai-orchestrator.evolution-cantiere-work.v1"
REQUIRED_GATES = (
    "implementation_tests_pass",
    "security_gates_pass",
    "regression_tests_pass",
    "library_contract_pass",
)
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
SAFE_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")


class EvolutionBridgeError(ValueError):
    pass


@dataclass(frozen=True)
class StagedEvolutionWork:
    work_id: str
    payload: dict[str, Any]

    def canonical_json(self) -> str:
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":")) + "\n"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvolutionBridgeError(message)


def stage_evolution_work(request: Mapping[str, Any]) -> StagedEvolutionWork:
    """Convert a sanitized Researcher implementation request into Library-owned work.

    This is a control-plane boundary only: source code and executable payloads are
    deliberately not accepted here. Cantiere must create its implementation in an
    isolated workspace and return validated reusable output through Library intake.
    """
    _require(request.get("request_type") == "library_module_improvement", "invalid request_type")
    proposal_id = str(request.get("proposal_id") or "")
    capability_id = str(request.get("capability_id") or "")
    _require(SAFE_ID.fullmatch(proposal_id) is not None, "invalid proposal_id")
    _require(SAFE_CAPABILITY.fullmatch(capability_id) is not None, "invalid capability_id")
    _require(
        request.get("mutation_policy") == "isolated_candidate_no_library_mutation",
        "unsafe mutation_policy",
    )

    objective = str(request.get("objective") or "").strip()
    _require(0 < len(objective) <= 1000, "invalid objective")

    raw_delta = request.get("knowledge_delta")
    _require(isinstance(raw_delta, (list, tuple)), "knowledge_delta must be a sequence")
    delta = tuple(str(item).strip() for item in raw_delta)
    _require(0 < len(delta) <= 64 and all(0 < len(item) <= 500 for item in delta), "invalid knowledge_delta")

    raw_gates = request.get("acceptance_gates")
    _require(isinstance(raw_gates, (list, tuple)), "acceptance_gates must be a sequence")
    gates = tuple(str(item) for item in raw_gates)
    _require(set(gates) == set(REQUIRED_GATES) and len(gates) == len(REQUIRED_GATES), "acceptance gates diverge from contract")

    forbidden = {"source", "source_code", "files", "payload", "patch", "diff", "commands"}
    _require(not (forbidden & set(request)), "executable/source payload is forbidden")

    identity = json.dumps(
        {"proposal_id": proposal_id, "capability_id": capability_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    work_id = "evo-" + hashlib.sha256(identity).hexdigest()[:24]
    payload = {
        "schema": SCHEMA,
        "state": "staged",
        "work_id": work_id,
        "proposal_id": proposal_id,
        "capability_id": capability_id,
        "objective": objective,
        "knowledge_delta": list(delta),
        "acceptance_gates": list(REQUIRED_GATES),
        "mutation_policy": "isolated_candidate_no_library_mutation",
        "required_output": {
            "type": "library_intake_bundle",
            "status": "discovered",
            "path_scope": "intake/<asset>/<version>",
        },
    }
    return StagedEvolutionWork(work_id=work_id, payload=payload)
