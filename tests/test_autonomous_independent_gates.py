"""Offline tests for independent GitHub Actions gate-step verification."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.autonomous_independent_gates import (
    LIBRARY_REPOSITORY, REQUIRED_STEPS, VALIDATE_WORKFLOW,
    _trusted_blob_sha, audit_library_ci_gates,
)

SHA = "a" * 40
IDENTITY = {
    "lane_id": "library-researcher", "state_version": 9,
    "claim_id": "claim", "packet_sha256": "b" * 64,
    "repository": LIBRARY_REPOSITORY,
    "pr_number": 120, "head_sha": SHA,
}
CI = {"repository": LIBRARY_REPOSITORY, "pr_number": 120, "head_sha": SHA,
      "verified_checks": {"validate": 7},
      "trusted_receipt": False, "completion_authorized": False}
BASE = f"https://api.github.com/repos/{LIBRARY_REPOSITORY}"
RUN = {
    "id": 99, "head_sha": SHA, "path": VALIDATE_WORKFLOW,
    "event": "pull_request", "status": "completed", "conclusion": "success",
    "repository": {"full_name": LIBRARY_REPOSITORY},
}
JOB = {
    "name": "validate", "run_id": 99, "head_sha": SHA,
    "status": "completed", "conclusion": "success",
    "check_run_url": f"{BASE}/check-runs/7",
    "steps": [{"name": name, "status": "completed", "conclusion": "success"}
              for name in REQUIRED_STEPS],
}


class IndependentGateAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        file = self.root / VALIDATE_WORKFLOW
        file.parent.mkdir(parents=True)
        file.write_text("name: Validate Module Library\n", encoding="utf-8")
        self.source = {"type": "file", "sha": _trusted_blob_sha(file)}

    def audit(self, *, source=None, runs=None, jobs=None, ci=None):
        data = [
            self.source if source is None else source,
            {"total_count": 1, "workflow_runs": [RUN]} if runs is None else runs,
            {"total_count": 1, "jobs": [JOB]} if jobs is None else jobs,
        ]
        with patch("tools.autonomous_independent_gates.fetch_json", side_effect=data) as fetch:
            result = audit_library_ci_gates(
                IDENTITY, CI if ci is None else ci, "fake-token",
                trusted_root=self.root,
            )
        return result, fetch

    def test_trusted_pipeline_success_does_not_authorize_completion(self):
        result, fetch = self.audit()
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(result["canonical_identity"], IDENTITY)
        self.assertEqual(result["validated_steps"], list(REQUIRED_STEPS))
        self.assertEqual(result["gate_assessment"]["G2_STATIC"], "CI_PIPELINE_STEPS_VERIFIED")
        self.assertEqual(result["gate_assessment"]["G3_CI"], "EXACT_HEAD_SUCCESS_VERIFIED")
        self.assertIn("PENDING", result["gate_assessment"]["G1_IMPLEMENTATION"])
        self.assertIn("PENDING", result["gate_assessment"]["G4_INTEGRATION"])
        self.assertIn("REQUIRES", result["gate_assessment"]["G5_TARGET_RUNTIME"])
        self.assertIs(result["trusted_receipt"], False)
        self.assertIs(result["completion_authorized"], False)

    def test_rejects_untrusted_pr_workflow_modification(self):
        with self.assertRaisesRegex(ValueError, "differs from protected"):
            self.audit(source={"type": "file", "sha": "f" * 40})

    def test_rejects_skipped_static_or_integration_step(self):
        for name in REQUIRED_STEPS:
            job = {**JOB, "steps": [
                {**step, "conclusion": "skipped"} if step["name"] == name else step
                for step in JOB["steps"]
            ]}
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "missing or unsuccessful"
            ):
                self.audit(jobs={"total_count": 1, "jobs": [job]})

    def test_rejects_unrelated_check_run_job(self):
        job = {**JOB, "check_run_url": f"{BASE}/check-runs/8"}
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.audit(jobs={"total_count": 1, "jobs": [job]})

    def test_rejects_unapproved_workflow_event(self):
        run = {**RUN, "event": "workflow_dispatch"}
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.audit(runs={"total_count": 1, "workflow_runs": [run]})

    def test_rejects_truncated_job_listing(self):
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            self.audit(jobs={"total_count": 2, "jobs": [JOB]})

    def test_rejects_unverified_or_forged_ci(self):
        for ci in (
            {**CI, "verified_checks": {"untrusted": 7}},
            {**CI, "verified_checks": {"validate": True}},
            {**CI, "trusted_receipt": True},
            {**CI, "completion_authorized": True},
        ):
            with self.subTest(ci=ci), patch(
                "tools.autonomous_independent_gates.fetch_json"
            ) as fetch:
                with self.assertRaises(ValueError):
                    audit_library_ci_gates(IDENTITY, ci, "fake-token", trusted_root=self.root)
                fetch.assert_not_called()

    def test_rejects_foreign_repository(self):
        with patch("tools.autonomous_independent_gates.fetch_json") as fetch:
            with self.assertRaisesRegex(ValueError, "unsupported"):
                audit_library_ci_gates(
                    {**IDENTITY, "repository": "owner/other"},
                    CI, "fake-token", trusted_root=self.root,
                )
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
