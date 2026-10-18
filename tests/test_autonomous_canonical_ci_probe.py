"""End-to-end unit tests for protected canonical lane / CI identity binding."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tools.autonomous_canonical_ci_probe import probe_canonical_lane
from tools.control_plane_manager import _review_packet_digest

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
REPO = "owner/repo"
SHA = "a" * 40
PR = {"number": 120, "state": "open", "draft": False,
      "base": {"ref": "main", "repo": {"full_name": REPO}},
      "head": {"sha": SHA, "repo": {"full_name": REPO}}}
CI = {"repository": REPO, "pr_number": 120, "head_sha": SHA,
      "verified_checks": {"Validate Module Library": 7},
      "trusted_receipt": False, "completion_authorized": False}


class CanonicalCIProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / ".airlab/control-plane"
        (folder / "workstreams").mkdir(parents=True)
        self.packet = {"schema_version": 1, "submitted_at": "2026-10-18T00:00:00Z",
                       "lane_id": "library-researcher", "claim_id": "claim",
                       "work_item": "work", "repository": REPO,
                       "summary": "candidate checked", "changes": ["module implementation"],
                       "evidence": [{"type": "ci", "ref": "workflow-run", "result": "PASS"}],
                       "known_risks": [], "reviewer_checks": ["verify integration"],
                       "roadmap_impact": {"material": False, "refs": []},
                       "pull_request": 120}
        self.lane = {"id": "library-researcher", "role": "worker",
                     "status": "REVIEW_REQUIRED", "state_version": 9,
                     "review_packet": self.packet,
                     "active_claim": {"claim_id": "claim", "work_item": "work",
                                      "repository": REPO,
                                      "lease_until": (NOW + timedelta(hours=1)).isoformat()}}
        self.canonical = {
            "schema_version": 1,
            "authority": {"repository": "pilialvu75-hue/AI-Orchestrator-Module-Library"},
            "workstreams": [".airlab/control-plane/workstreams/library-researcher.json"],
        }
        self.save()

    def save(self):
        folder = self.root / ".airlab/control-plane"
        (folder / "canonical-state.json").write_text(json.dumps(self.canonical))
        (folder / "workstreams/library-researcher.json").write_text(json.dumps(self.lane))

    def execute(self, pr=None, ci=None):
        with patch("tools.autonomous_canonical_ci_probe.fetch_json",
                   return_value=PR if pr is None else pr) as fetch, patch(
                       "tools.autonomous_canonical_ci_probe.probe_ci",
                       return_value=CI if ci is None else ci) as probe:
            result = probe_canonical_lane(
                "library-researcher", REPO, 120, ["Validate Module Library"],
                "test-token", root=self.root, now=NOW,
            )
        return result, fetch, probe

    def test_protected_probe_emits_live_canonical_identity_without_authority(self):
        evidence, fetch, probe = self.execute()
        self.assertEqual(evidence["canonical_identity"], {
            "lane_id": "library-researcher", "state_version": 9,
            "claim_id": "claim", "packet_sha256": _review_packet_digest(self.packet),
            "repository": REPO, "pr_number": 120, "head_sha": SHA,
        })
        self.assertFalse(evidence["trusted_receipt"])
        self.assertFalse(evidence["completion_authorized"])
        fetch.assert_called_once_with("https://api.github.com/repos/owner/repo/pulls/120", "test-token")
        probe.assert_called_once()

    def test_protected_workflow_attaches_independent_gate_audit(self):
        audit_result = {
            "canonical_identity": {
                "lane_id": "library-researcher", "state_version": 9,
                "claim_id": "claim", "packet_sha256": _review_packet_digest(self.packet),
                "repository": REPO, "pr_number": 120, "head_sha": SHA,
            },
            "trusted_receipt": False, "completion_authorized": False,
        }
        with patch("tools.autonomous_canonical_ci_probe.fetch_json",
                   return_value=PR), patch(
                       "tools.autonomous_canonical_ci_probe.probe_ci",
                       return_value=CI), patch(
                       "tools.autonomous_canonical_ci_probe.audit_library_ci_gates",
                       return_value=audit_result) as audit:
            result = probe_canonical_lane(
                "library-researcher", REPO, 120, ["Validate Module Library"],
                "test-token", root=self.root, now=NOW, audit_ci_pipeline=True,
            )
        self.assertEqual(result["independent_gate_audit"], audit_result)
        self.assertIs(result["completion_authorized"], False)
        audit.assert_called_once_with(
            result["canonical_identity"], CI, "test-token", trusted_root=self.root,
        )

    def test_rejects_ci_verification_from_different_head(self):
        with self.assertRaisesRegex(ValueError, "differs from live GitHub CI"):
            self.execute(ci={**CI, "head_sha": "f" * 40})

    def test_rejects_expired_claim_without_api_calls(self):
        self.lane["active_claim"]["lease_until"] = (NOW - timedelta(minutes=1)).isoformat()
        self.save()
        with patch("tools.autonomous_canonical_ci_probe.fetch_json") as fetch:
            with self.assertRaisesRegex(ValueError, "lease expired"):
                self.execute()
            fetch.assert_not_called()

    def test_rejects_workstream_missing_or_renamed(self):
        self.lane["id"] = "other-lane"
        self.save()
        with self.assertRaisesRegex(ValueError, "exist exactly once"):
            self.execute()

    def test_rejects_untrusted_canonical_authority(self):
        self.canonical["authority"]["repository"] = "attacker/repo"
        self.save()
        with self.assertRaisesRegex(ValueError, "untrusted canonical snapshot"):
            self.execute()

    def test_rejects_path_traversal_from_canonical_registry(self):
        self.canonical["workstreams"] = ["../../unauthorized.json"]
        self.save()
        with self.assertRaisesRegex(ValueError, "invalid canonical workstream path|escapes protected directory"):
            self.execute()

    def test_rejects_wrong_packet_pr_or_commit(self):
        self.packet["pull_request"] = 121
        self.save()
        with self.assertRaisesRegex(ValueError, "PR number"):
            self.execute()
        self.packet["pull_request"] = 120
        self.save()
        with self.assertRaisesRegex(ValueError, "PR head"):
            self.execute(pr={**PR, "head": {"sha": "invalid"}})


if __name__ == "__main__":
    unittest.main()
