"""Integration tests for read-only protected receipt evidence probe."""
import unittest
from unittest.mock import patch

from tools.autonomous_receipt_evidence_probe import probe_receipt_evidence

IDENTITY = {"lane_id": "library", "state_version": 9, "claim_id": "claim",
            "packet_sha256": "b" * 64, "repository": "owner/repo",
            "pr_number": 120, "head_sha": "a" * 40}
RUN = {"repository": "owner/repo", "head_sha": "c" * 40,
       "run_id": 55, "run_attempt": 1,
       "workflow_path": ".github/workflows/autonomous-ci-probe.yml",
       "authenticated": False, "completion_authorized": False}


def probe(receipt):
    return probe_receipt_evidence(
        receipt=receipt, canonical_identity=IDENTITY,
        protected_repository="owner/repo", run_id=55, run_attempt=1,
        workflow_path=".github/workflows/autonomous-ci-probe.yml",
        protected_sha="c" * 40, github_token="test-token",
    )


class ReceiptEvidenceProbeTests(unittest.TestCase):
    @patch("tools.autonomous_receipt_evidence_probe.fetch_ci_evidence_artifact", return_value={"repository": "owner/repo", "pr_number": 120,
        "head_sha": "a" * 40, "verified_checks": {"Validate Module Library": 7},
        "protected_run_id": 55, "protected_run_attempt": 1,
        "protected_workflow_ref": "owner/repo/.github/workflows/autonomous-ci-probe.yml@refs/heads/main",
        "trusted_receipt": False, "completion_authorized": False})
    @patch("tools.autonomous_receipt_evidence_probe.fetch_json", return_value={
        "total_count": 1, "artifacts": [{"id": 42, "name": "autonomous-ci-evidence",
                                         "expired": False, "workflow_run": {"id": 55}}],
    })
    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run", return_value=RUN)
    def test_combines_read_only_evidence(self, fetch, artifacts, download):
        result = probe(IDENTITY.copy())
        self.assertEqual(result["identity"], IDENTITY)
        self.assertEqual(result["artifact_id"], 42)
        self.assertEqual(result["ci_evidence"]["head_sha"], IDENTITY["head_sha"])
        download.assert_called_once_with("owner/repo", 42, "test-token")
        self.assertFalse(result["trusted_receipt"])
        self.assertFalse(result["completion_authorized"])
        fetch.assert_called_once()

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run")
    def test_forged_receipt_rejected_before_api_fetch(self, fetch):
        with self.assertRaises(ValueError):
            probe({**IDENTITY, "claim_id": "forged"})
        fetch.assert_not_called()

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run")
    def test_rejects_protected_repository_mismatch_before_fetch(self, fetch):
        with self.assertRaisesRegex(ValueError, "protected repository does not match"):
            probe_receipt_evidence(
                receipt=IDENTITY.copy(), canonical_identity=IDENTITY,
                protected_repository="other/repo", run_id=55, run_attempt=1,
                workflow_path=".github/workflows/autonomous-ci-probe.yml",
                protected_sha="c" * 40, github_token="test-token",
            )
        fetch.assert_not_called()

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run",
           return_value={**RUN, "head_sha": "d" * 40})
    def test_wrong_protected_run_sha_rejected(self, fetch):
        with self.assertRaises(ValueError):
            probe(IDENTITY.copy())


    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run", return_value=RUN)
    def test_rejects_missing_expired_duplicate_or_wrong_run_artifact(self, fetch):
        valid = {"id": 42, "name": "autonomous-ci-evidence",
                 "expired": False, "workflow_run": {"id": 55}}
        cases = (
            [],
            [{**valid, "expired": True}],
            [valid, {**valid, "id": 43}],
            [{**valid, "workflow_run": {"id": 56}}],
            [{**valid, "id": True}],
        )
        for artifacts in cases:
            with self.subTest(artifacts=artifacts), patch(
                "tools.autonomous_receipt_evidence_probe.fetch_json",
                return_value={"total_count": len(artifacts), "artifacts": artifacts},
            ):
                with self.assertRaises(ValueError):
                    probe(IDENTITY.copy())

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run", return_value=RUN)
    @patch("tools.autonomous_receipt_evidence_probe.fetch_json", return_value={
        "total_count": 1, "artifacts": [{"id": 42, "name": "autonomous-ci-evidence",
                                        "expired": False, "workflow_run": {"id": 55}}],
    })
    def test_rejects_forged_or_incomplete_ci_evidence(self, artifacts, run):
        valid = {"repository": "owner/repo", "pr_number": 120,
                 "head_sha": "a" * 40, "verified_checks": {"Validate Module Library": 7},
                 "protected_run_id": 55, "protected_run_attempt": 1,
                 "protected_workflow_ref": "owner/repo/.github/workflows/autonomous-ci-probe.yml@refs/heads/main",
                 "trusted_receipt": False, "completion_authorized": False}
        cases = (
            {**valid, "repository": "other/repo"},
            {**valid, "pr_number": 121},
            {**valid, "head_sha": "f" * 40},
            {**valid, "trusted_receipt": True},
            {**valid, "completion_authorized": True},
            {**valid, "verified_checks": {}},
            {**valid, "verified_checks": {"Validate Module Library": True}},
            {**valid, "verified_checks": {"Validate Module Library": -1}},
            {**valid, "verified_checks": {"": 7}},
            {key: value for key, value in valid.items() if key != "head_sha"},
        )
        for evidence in cases:
            with self.subTest(evidence=evidence), patch(
                "tools.autonomous_receipt_evidence_probe.fetch_ci_evidence_artifact",
                return_value=evidence,
            ):
                with self.assertRaises(ValueError):
                    probe(IDENTITY.copy())

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run", return_value=RUN)
    @patch("tools.autonomous_receipt_evidence_probe.fetch_json", return_value={
        "total_count": 1, "artifacts": [{"id": 42, "name": "autonomous-ci-evidence",
                                        "expired": False, "workflow_run": {"id": 55}}],
    })
    def test_rejects_unexpected_evidence_fields(self, artifacts, run):
        evidence = {"repository": "owner/repo", "pr_number": 120,
                    "head_sha": "a" * 40, "verified_checks": {"Validate Module Library": 7},
                    "protected_run_id": 55, "protected_run_attempt": 1,
                    "protected_workflow_ref": "owner/repo/.github/workflows/autonomous-ci-probe.yml@refs/heads/main",
                    "trusted_receipt": False, "completion_authorized": False,
                    "worker_claimed_approval": True}
        with patch("tools.autonomous_receipt_evidence_probe.fetch_ci_evidence_artifact",
                   return_value=evidence):
            with self.assertRaisesRegex(ValueError, "protected CI evidence"):
                probe(IDENTITY.copy())

    def test_rejects_wrong_run_identity(self):
        for field, value in (("run_id", 56), ("run_attempt", 2),
                             ("workflow_path", ".github/workflows/other.yml"),
                             ("authenticated", True), ("completion_authorized", True)):
            with self.subTest(field=field), patch(
                "tools.autonomous_receipt_evidence_probe.fetch_protected_run",
                return_value={**RUN, field: value},
            ):
                with self.assertRaises(ValueError):
                    probe(IDENTITY.copy())


if __name__ == "__main__":
    unittest.main()
