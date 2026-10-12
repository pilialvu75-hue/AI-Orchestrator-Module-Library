from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from library_evolution_queue import EvolutionWorkQueue


class EvolutionDispatchError(ValueError):
    pass


def prepare_claim(root: Path, work_id: str) -> dict[str, Any]:
    """Prepare a Library-owned Cantiere claim without mutating queue state."""
    queue = EvolutionWorkQueue(root)
    work = queue.load(work_id)
    if work is None:
        raise EvolutionDispatchError("unknown work_id")
    if work.get("state") != "staged":
        raise EvolutionDispatchError("only staged work may be prepared")
    return _claim_envelope(work_id, work)


def resume_claim(root: Path, work_id: str) -> dict[str, Any]:
    """Reconstruct an existing claimed envelope without another transition.

    This is a read-only recovery operation, not a new claim or an apply gate.
    """
    queue = EvolutionWorkQueue(root)
    work = queue.load(work_id)
    if work is None:
        raise EvolutionDispatchError("unknown work_id")
    if work.get("state") != "claimed":
        raise EvolutionDispatchError("only claimed work may be resumed")
    return _claim_envelope(work_id, work)


def _claim_envelope(work_id: str, work: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "ai-orchestrator.evolution-cantiere-claim.v1",
        "work_id": work_id,
        "proposal_id": work["proposal_id"],
        "capability_id": work["capability_id"],
        "objective": work["objective"],
        "knowledge_delta": list(work["knowledge_delta"]),
        "acceptance_gates": list(work["acceptance_gates"]),
        "mutation_policy": work["mutation_policy"],
        "required_output": dict(work["required_output"]),
        "source": "library_evolution_queue",
    }


def claim(root: Path, work_id: str) -> dict[str, Any]:
    """Persist the claim only after the caller has accepted the prepared envelope."""
    queue = EvolutionWorkQueue(root)
    envelope = prepare_claim(root, work_id)
    result = queue.transition(work_id, "claimed")
    return {"claim": envelope, "transition": result}


def write_claim(envelope: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
