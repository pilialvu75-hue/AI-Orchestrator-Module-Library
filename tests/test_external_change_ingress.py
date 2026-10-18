import importlib.util
import argparse
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_cross_repo_permission_denial_preserves_readable_repo_results(self):
        registry = self._registry()
        registry["tracked_repositories"].append({
            "repository": "owner/private",
            "baseline_at": "2026-10-03T10:00:00Z",
            "cursor_merged_at": "2026-10-03T10:00:00Z",
        })

        def fake_fetch(one, token):
            repo = one["tracked_repositories"][0]["repository"]
            if repo == "owner/private":
                raise RuntimeError(
                    "GitHub API 403 for https://api.github.com/repos/owner/private/pulls: "
                    "Resource not accessible by integration"
                )
            return {repo: [self._pr()]}
        with patch.object(module, "fetch_changes", side_effect=fake_fetch):
            changes, failures = module.fetch_changes_partially(registry, "token")
        self.assertEqual(changes, {"owner/app": [self._pr()]})
        self.assertEqual(failures, {"owner/private": "GITHUB_ACCESS_403"})
        updated = module.scan_registry(registry, [], changes, now="2026-10-03T11:05:00Z")
        module.record_scan_health(updated, changes, failures, now="2026-10-03T11:05:00Z")
        self.assertEqual(updated["tracked_repositories"][0]["cursor_merged_at"], "2026-10-03T11:00:00Z")
        self.assertEqual(updated["tracked_repositories"][1]["cursor_merged_at"], "2026-10-03T10:00:00Z")
        self.assertEqual(updated["scan_health"]["owner/private"]["state"], "UNAVAILABLE")
        self.assertEqual(len(updated["incidents"]), 1)

    def test_scan_persists_partial_work_and_check_refuses_inaccessible_sources(self):
        registry = self._registry()
        registry["tracked_repositories"].append({
            "repository": "owner/private",
            "baseline_at": "2026-10-03T10:00:00Z",
            "cursor_merged_at": "2026-10-03T10:00:00Z",
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "external.json"
            path.write_text(json.dumps(registry))
            args = argparse.Namespace(registry=str(path), token="fake-token", now="2026-10-03T11:00:00Z")
            with patch.object(module, "fetch_changes_partially", return_value=(
                {"owner/app": []}, {"owner/private": "GITHUB_ACCESS_403"}
            )), patch.object(module, "_workstreams", return_value=[]):
                self.assertEqual(module.cmd_scan(args), 0)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["scan_health"]["owner/app"]["state"], "OK")
            self.assertEqual(saved["scan_health"]["owner/private"]["error_code"], "GITHUB_ACCESS_403")
            self.assertEqual(saved["tracked_repositories"][1]["cursor_merged_at"], "2026-10-03T10:00:00Z")
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(module.cmd_check(argparse.Namespace(registry=str(path))), 1)
                self.assertIn("SOURCE_UNAVAILABLE: owner/private", stderr.getvalue())
            with patch.object(module, "fetch_changes_partially", return_value=(
                {"owner/app": [], "owner/private": []}, {}
            )), patch.object(module, "_workstreams", return_value=[]):
                self.assertEqual(module.cmd_scan(args), 0)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["scan_health"]["owner/private"]["state"], "OK")
            self.assertIsNone(saved["scan_health"]["owner/private"]["error_code"])
            self.assertEqual(module.cmd_check(argparse.Namespace(registry=str(path))), 0)

    def test_unknown_api_error_fails_without_fabricating_scan_health(self):
        with patch.object(module, "fetch_changes", side_effect=RuntimeError("GitHub API 500")):
            with self.assertRaisesRegex(RuntimeError, "API 500"):
                module.fetch_changes_partially(self._registry(), "token")

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
