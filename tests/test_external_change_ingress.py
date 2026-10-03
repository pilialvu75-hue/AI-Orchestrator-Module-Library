import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "external_change_ingress",
    ROOT / "tools" / "external_change_ingress.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ExternalChangeIngressTests(unittest.TestCase):
    def _registry(self):
        return {
            "schema_version": 1,
            "policy": {
                "mode": "incremental_after_baseline",
                "canonical_progress_requires_reconciliation": True,
            },
            "tracked_repositories": [{
                "repository": "owner/app",
                "baseline_at": "2026-10-03T10:00:00Z",
                "cursor_merged_at": "2026-10-03T10:00:00Z",
            }],
            "incidents": [],
            "reconciliation_history": [],
            "last_scan_at": None,
        }

    def _pr(self, number=12, branch="feature/x", merge_sha="abc1234def5678"):
        return {
            "kind": "pull_request",
            "repository": "owner/app",
            "pull_request": number,
            "merged_at": "2026-10-03T11:00:00Z",
            "merge_sha": merge_sha,
            "head_branch": branch,
            "base_branch": "main",
            "title": "Change X",
            "html_url": "https://github.com/owner/app/pull/12",
        }

    def test_unclaimed_merged_pr_becomes_persistent_incident(self):
        registry = module.scan_registry(
            self._registry(),
            [],
            {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        self.assertEqual(len(registry["incidents"]), 1)
        incident = registry["incidents"][0]
        self.assertEqual(incident["status"], "UNRECONCILED")
        self.assertEqual(incident["pull_request"], 12)
        self.assertEqual(registry["tracked_repositories"][0]["cursor_merged_at"], "2026-10-03T11:00:00Z")
        self.assertEqual(len(module.unresolved_incidents(registry)), 1)

    def test_active_claim_on_same_repository_and_branch_matches_merge(self):
        lanes = [{
            "id": "cantiere",
            "active_claim": {
                "claim_id": "claim-1",
                "repository": "owner/app",
                "branch": "feature/x",
            },
        }]
        registry = module.scan_registry(
            self._registry(),
            lanes,
            {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        self.assertEqual(registry["incidents"], [])

    def test_checkpoint_pr_reference_matches_after_claim_release(self):
        lanes = [{
            "id": "main-reviewer",
            "active_claim": None,
            "checkpoints": [{"evidence_refs": ["owner/app#12"]}],
        }]
        registry = module.scan_registry(
            self._registry(),
            lanes,
            {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        self.assertEqual(registry["incidents"], [])

    def test_merge_sha_evidence_matches(self):
        lanes = [{
            "id": "main-reviewer",
            "completed_work": [{"evidence": [{"ref": "merge:abc1234def5678", "result": "PASS"}]}],
        }]
        registry = module.scan_registry(
            self._registry(),
            lanes,
            {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        self.assertEqual(registry["incidents"], [])

    def test_same_pr_number_in_other_repository_does_not_match(self):
        lanes = [{
            "id": "other",
            "checkpoints": [{"evidence_refs": ["owner/other#12"]}],
        }]
        registry = module.scan_registry(
            self._registry(),
            lanes,
            {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        self.assertEqual(len(registry["incidents"]), 1)

    def test_direct_commit_without_evidence_becomes_incident(self):
        change = {
            "kind": "direct_commit",
            "repository": "owner/app",
            "commit_sha": "deadbeef1234567890",
            "committed_at": "2026-10-03T11:30:00Z",
            "base_branch": "main",
            "message": "Direct main change",
            "html_url": "https://github.com/owner/app/commit/deadbeef",
        }
        registry = module.scan_registry(
            self._registry(),
            [],
            {"owner/app": [change]},
            now="2026-10-03T11:35:00Z",
        )
        self.assertEqual(registry["incidents"][0]["kind"], "direct_commit")
        self.assertEqual(registry["incidents"][0]["commit_sha"], "deadbeef1234567890")

    def test_scan_is_idempotent_after_cursor_advance(self):
        registry = module.scan_registry(
            self._registry(),
            [],
            {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        registry = module.scan_registry(
            registry,
            [],
            {"owner/app": [self._pr()]},
            now="2026-10-03T12:05:00Z",
        )
        self.assertEqual(len(registry["incidents"]), 1)

    def test_reconciled_incident_requires_main_reviewer_and_evidence(self):
        registry = self._registry()
        registry["incidents"] = [{
            "incident_id": "incident-1",
            "status": "RECONCILED",
            "repository": "owner/app",
            "reconciliation": {
                "reviewed_by": "main-reviewer",
                "evidence_refs": ["owner/app#12", "claim:reconciled-1"],
            },
        }]
        self.assertEqual(module.validate_registry(registry), [])
        registry["incidents"][0]["reconciliation"]["evidence_refs"] = []
        self.assertTrue(any("evidence_refs" in error for error in module.validate_registry(registry)))

    def test_baseline_prevents_historical_backfill(self):
        old = self._pr()
        old["merged_at"] = "2026-10-03T09:59:59Z"
        registry = module.scan_registry(
            self._registry(),
            [],
            {"owner/app": [old]},
            now="2026-10-03T11:05:00Z",
        )
        self.assertEqual(registry["incidents"], [])
        self.assertEqual(registry["tracked_repositories"][0]["cursor_merged_at"], "2026-10-03T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
