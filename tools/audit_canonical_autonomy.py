#!/usr/bin/env python3
"""Read-only audit of canonical-state autonomy prerequisites."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(root: Path = ROOT) -> dict:
    cp = root / ".airlab/control-plane"
    canonical = json.loads((cp / "canonical-state.json").read_text())
    gates = json.loads((cp / "gates.json").read_text())
    registry = json.loads((cp / "automation-registry.json").read_text())
    workflow = (root / ".github/workflows/control-plane-reconcile.yml").read_text()
    ids = {item["id"] for item in gates["gates"]}
    automations = registry.get("automations", [])
    reviewer_actors = [a["actor_id"] for a in automations if a.get("enabled") and a.get("kind") == "reviewer"]
    inbox = (root / "tools/control_plane_inbox.py").read_text() if (root / "tools/control_plane_inbox.py").exists() else ""
    manager = (root / "tools/control_plane_manager.py").read_text() if (root / "tools/control_plane_manager.py").exists() else ""
    findings = {
        "inbox_reviewer_authority_binding": "main-reviewer authority" in inbox or 'owner_lane") == "main-reviewer"' in inbox,
        "manager_reviewer_promotion_binding": '"reviewed_by": "main-reviewer"' in manager,
        "manual_reviewer_gate": "G6_REVIEWER" in ids,
        "manual_reviewer_promotion": canonical.get("promotion_policy", {}).get("verified_by") == "main-reviewer",
        "automated_reviewer_registered": bool(reviewer_actors),
        "scheduled_reconciliation": "schedule:" in workflow and "control_plane_manager.py reconcile" in workflow,
        "transactional_inbox": "control_plane_inbox.py process" in workflow,
        "physical_evidence_required": bool(canonical.get("promotion_policy", {}).get("runtime_or_hardware_claims_require_target_runtime_evidence")),
    }
    return {
        "schema_version": 1,
        "read_only": True,
        "autonomous_promotion_ready": not (
            findings["manual_reviewer_gate"] or findings["manual_reviewer_promotion"] or findings["inbox_reviewer_authority_binding"] or findings["manager_reviewer_promotion_binding"]
        ),
        "findings": findings,
        "enabled_reviewer_actor_count": len(reviewer_actors),
        "next_action": "Implement and test independent automated verification and atomic policy migration" if findings["manual_reviewer_gate"] or findings["manual_reviewer_promotion"] else "Validate automated promotion with exact-head CI and negative tests",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
