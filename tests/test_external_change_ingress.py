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

    def test_repository_metadata_probe_uses_canonical_github_api_url(self):
        # GitHub REST can 404 on /repos/OWNER/REPO/ (trailing slash).
        # The anonymous public probe introduced for repo-scoped tokens must
        # use the documented /repos/OWNER/REPO URL instead.
        with patch.object(module, "_api_get", return_value={
            "full_name": "owner/public", "private": False
        }) as get:
            metadata = module._repo_api("owner/public", "", None)
        self.assertEqual(metadata["private"], False)
        get.assert_called_once_with(
            "https://api.github.com/repos/owner/public", None
        )

    def test_repository_child_endpoints_keep_exact_one_slash(self):
        with patch.object(module, "_api_get", return_value=[]) as get:
            module._repo_api("owner/public", "pulls?state=closed", "token")
        get.assert_called_once_with(
            "https://api.github.com/repos/owner/public/pulls?state=closed",
            "token",
        )

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

    def test_cross_repo_404_retries_only_a_verified_public_source(self):
        registry = self._registry()
        seen_tokens = []

        def fake_fetch(one, token):
            seen_tokens.append(token)
            repo = one["tracked_repositories"][0]["repository"]
            if token == "repo-scoped-token":
                raise RuntimeError(
                    f"GitHub API 404 for https://api.github.com/repos/{repo}/pulls: Not Found"
                )
            return {repo: [self._pr()]}

        with patch.object(module, "fetch_changes", side_effect=fake_fetch), \
             patch.object(module, "_repo_api", return_value={
                 "private": False, "full_name": "owner/app"
             }) as repo_probe:
            verified, failures = module.fetch_changes_partially(
                registry, "repo-scoped-token"
            )

        self.assertEqual(verified, {"owner/app": [self._pr()]})
        self.assertEqual(failures, {})
        self.assertEqual(seen_tokens, ["repo-scoped-token", None])
        repo_probe.assert_called_once_with("owner/app", "", None)

        changed = module.scan_registry(
            registry, [], verified, now="2026-10-03T11:05:00Z"
        )
        self.assertEqual(
            changed["tracked_repositories"][0]["cursor_merged_at"],
            "2026-10-03T11:00:00Z"
        )

    def test_cross_repo_404_private_source_does_not_downgrade_or_advance(self):
        registry = self._registry()
        registry["tracked_repositories"][0]["repository"] = "owner/private"
        original_cursor = registry["tracked_repositories"][0]["cursor_merged_at"]
        for probe in [
            {"private": True, "full_name": "owner/private"},
            {"private": False, "full_name": "owner/different"},
        ]:
            with self.subTest(probe=probe), \
                 patch.object(module, "fetch_changes", side_effect=RuntimeError(
                     "GitHub API 404 for https://api.github.com/repos/owner/private/pulls: Not Found"
                 )) as get_changes, \
                 patch.object(module, "_repo_api", return_value=probe):
                verified, failures = module.fetch_changes_partially(
                    registry, "repo-scoped-token"
                )
                self.assertEqual(verified, {})
                self.assertEqual(
                    failures,
                    {"owner/private": "GITHUB_NOT_FOUND_OR_INACCESSIBLE_404"},
                )
                get_changes.assert_called_once()
                module.scan_registry(registry, [], verified, now="2026-10-03T11:05:00Z")
                self.assertEqual(
                    registry["tracked_repositories"][0]["cursor_merged_at"],
                    original_cursor,
                )

    def test_cross_repo_404_anonymous_probe_error_stays_unavailable(self):
        registry = self._registry()
        with patch.object(module, "fetch_changes", side_effect=RuntimeError(
                "GitHub API 404 for https://api.github.com/repos/owner/app/pulls: Not Found"
             )), patch.object(module, "_repo_api", side_effect=RuntimeError(
                "GitHub API 403 for https://api.github.com/repos/owner/app: rate limited"
             )):
            verified, failures = module.fetch_changes_partially(
                registry, "repo-scoped-token"
            )
        self.assertEqual(verified, {})
        self.assertEqual(failures, {"owner/app": "GITHUB_NOT_FOUND_OR_INACCESSIBLE_404"})

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

    def test_monitor_reports_unreconciled_without_claiming_certification(self):
        registry = module.scan_registry(
            self._registry(), [], {"owner/app": [self._pr()]},
            now="2026-10-03T11:05:00Z",
        )
        module.record_scan_health(
            registry, {"owner/app": [self._pr()]}, {},
            now="2026-10-03T11:05:00Z",
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                status = module.cmd_check(argparse.Namespace(
                    registry=str(path), monitor_only=True,
                ))
            self.assertEqual(status, 0)
            self.assertIn("UNRECONCILED:", stderr.getvalue())
            self.assertIn("::warning title=External changes", stderr.getvalue())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["incidents"][0]["status"], "UNRECONCILED")
            self.assertIsNone(saved["incidents"][0]["reconciliation"])
            # Strict validation remains a failing gate for progress attribution.
            with patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(
                    module.cmd_check(argparse.Namespace(registry=str(path))),
                    1,
                )

    def test_monitor_never_passes_when_source_coverage_is_incomplete(self):
        registry = self._registry()
        registry["incidents"] = [{
            "incident_id": "one",
            "status": "UNRECONCILED",
            "repository": "owner/app",
            "pull_request": 12,
            "reconciliation": None,
        }]
        registry["scan_health"] = {
            "owner/app": {
                "state": "UNAVAILABLE",
                "error_code": "GITHUB_NOT_FOUND_OR_INACCESSIBLE_404",
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                status = module.cmd_check(argparse.Namespace(
                    registry=str(path), monitor_only=True,
                ))
            self.assertEqual(status, 1)
            self.assertIn("SOURCE_UNAVAILABLE:", stderr.getvalue())
            self.assertIn("UNRECONCILED:", stderr.getvalue())

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
