from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from library_evolution_dispatch import EvolutionDispatchError, _claim_envelope
from library_evolution_queue import EvolutionWorkQueue


def preview_legacy_reconciliation(root: Path, work_id: str, historical_staged: dict[str, Any]) -> dict[str, Any]:
    """Read-only reconciliation preview; does not authorize or mutate a claim.

    The caller must source historical_staged from a separately verified immutable
    Git blob. A mutable queue record is never acceptable as historical evidence.
    """
    queue = EvolutionWorkQueue(root)
    current = queue.load(work_id)
    if current is None or current.get("state") != "claimed":
        raise EvolutionDispatchError("legacy reconciliation requires claimed work")
    if "claimed_envelope" in current or "claimed_envelope_sha256" in current:
        raise EvolutionDispatchError("work is already attested; use normal resume")
    if not isinstance(historical_staged, dict):
        raise EvolutionDispatchError("historical staged evidence must be an object")
    if historical_staged.get("schema") != current.get("schema"):
        raise EvolutionDispatchError("historical queue schema mismatch")
    if historical_staged.get("work_id") != work_id or historical_staged.get("state") != "staged":
        raise EvolutionDispatchError("invalid historical staged identity/state")
    original = {key: value for key, value in historical_staged.items() if key != "state"}
    present = {key: value for key, value in current.items() if key != "state"}
    if original != present:
        raise EvolutionDispatchError("current claim differs from historical staged evidence")
    envelope = _claim_envelope(work_id, historical_staged)
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "work_id": work_id,
        "historical_envelope": envelope,
        "proposed_sha256": digest,
        "action": "REVIEW_REQUIRED",
        "queue_mutated": False,
    }
