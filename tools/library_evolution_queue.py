from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from library_evolution_bridge import StagedEvolutionWork

QUEUE_SCHEMA = "ai-orchestrator.evolution-work-queue.v1"
TRANSITIONS = {
    "staged": {"claimed"},
    "claimed": {"returned", "failed"},
    "returned": set(),
    "failed": set(),
}


class EvolutionQueueError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvolutionQueueError(message)


class EvolutionWorkQueue:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.queue_root = self.root / "evolution-work"

    def _path(self, work_id: str) -> Path:
        _require(
            work_id.startswith("evo-")
            and len(work_id) == 28
            and all(ch in "0123456789abcdef" for ch in work_id[4:]),
            "invalid work_id",
        )
        return self.queue_root / f"{work_id}.json"

    @staticmethod
    def _canonical(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def load(self, work_id: str) -> dict[str, Any] | None:
        path = self._path(work_id)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvolutionQueueError(f"invalid queued work: {work_id}") from exc
        _require(isinstance(value, dict), "queued work must be an object")
        _require(value.get("schema") == QUEUE_SCHEMA, "invalid queue schema")
        _require(value.get("work_id") == work_id, "queued work identity mismatch")
        _require(value.get("state") in TRANSITIONS, "invalid queued work state")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        path = self._path(str(value["work_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def stage(self, work: StagedEvolutionWork) -> dict[str, Any]:
        value = dict(work.payload)
        _require(value.get("state") == "staged", "only staged work may enter queue")
        value["schema"] = QUEUE_SCHEMA
        existing = self.load(work.work_id)
        if existing is not None:
            _require(
                self._canonical(existing) == self._canonical(value),
                "work_id already exists with divergent content",
            )
            return {"result": "already_staged", "work_id": work.work_id, "state": "staged"}
        self._write(value)
        return {"result": "staged", "work_id": work.work_id, "state": "staged"}

    def transition(
        self,
        work_id: str,
        target: str,
        *,
        receipt: dict[str, Any] | None = None,
        claim_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.load(work_id)
        _require(current is not None, "unknown work_id")
        source = str(current["state"])
        if source == target:
            return {"result": "already_transitioned", "work_id": work_id, "state": target}
        _require(target in TRANSITIONS[source], f"invalid transition {source} -> {target}")
        if target == "claimed":
            _require(isinstance(claim_evidence, dict), "claim transition requires evidence")
            _require(isinstance(claim_evidence.get("claimed_envelope"), dict), "missing claimed envelope")
            _require(isinstance(claim_evidence.get("claimed_envelope_sha256"), str), "missing claimed digest")
            current.update(claim_evidence)
        else:
            _require(claim_evidence is None, "claim evidence only valid on claim transition")
        if target in {"returned", "failed"}:
            _require(isinstance(receipt, dict) and bool(receipt), "terminal transition requires receipt")
            current["receipt"] = receipt
        else:
            _require(receipt is None, "receipt is only valid for terminal transition")
        current["state"] = target
        self._write(current)
        return {"result": "transitioned", "work_id": work_id, "state": target}
