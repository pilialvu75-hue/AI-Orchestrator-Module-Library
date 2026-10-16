from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_canonical_autonomy import audit


class CanonicalAutonomyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".airlab/control-plane").mkdir(parents=True)
        (self.root / ".github/workflows").mkdir(parents=True)
        self.cp = self.root / ".airlab/control-plane"
        self.write("canonical-state.json", {"promotion_policy": {"verified_by": "main-reviewer", "runtime_or_hardware_claims_require_target_runtime_evidence": True}})
        self.write("gates.json", {"gates": [{"id": "G6_REVIEWER"}]})
        self.write("automation-registry.json", {"automations": [{"actor_id": "automation:reviewer", "enabled": True, "kind": "reviewer"}]})
        (self.root / ".github/workflows/control-plane-reconcile.yml").write_text("schedule:\n  - cron: '17 * * * *'\nrun: control_plane_inbox.py process && control_plane_manager.py reconcile\n")

    def write(self, name, data):
        (self.cp / name).write_text(json.dumps(data))

    def test_reports_blocked_promotion(self):
        result = audit(self.root)
        self.assertFalse(result["autonomous_promotion_ready"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["findings"]["physical_evidence_required"])

    def test_read_only(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        audit(self.root)
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_detects_migrated_policy(self):
        self.write("gates.json", {"gates": [{"id": "G3_CI"}]})
        self.write("canonical-state.json", {"promotion_policy": {"verified_by": "automated-verifier", "runtime_or_hardware_claims_require_target_runtime_evidence": True}})
        self.assertTrue(audit(self.root)["autonomous_promotion_ready"])


if __name__ == "__main__":
    unittest.main()
