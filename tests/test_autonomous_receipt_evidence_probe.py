"""Integration tests for read-only protected receipt evidence probe."""
import unittest
from unittest.mock import patch

from tools.autonomous_receipt_evidence_probe import probe_receipt_evidence

IDENTITY = {"lane_id": "library", "state_version": 9, "claim_id": "claim",
            "packet_sha256": "b" * 64, "repository": "owner/repo",
            "pr_number": 120, "head_sha": "a" * 40}
RUN = {"repository": "owner/repo", "head_sha": "c" * 40,
       "authenticated": False, "completion_authorized": False}


def probe(receipt):
    return probe_receipt_evidence(
        receipt=receipt, canonical_identity=IDENTITY,
        protected_repository="owner/repo", run_id=55, run_attempt=1,
        workflow_path=".github/workflows/autonomous-ci-probe.yml",
        protected_sha="c" * 40, github_token="test-token",
    )


class ReceiptEvidenceProbeTests(unittest.TestCase):
    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run", return_value=RUN)
    def test_combines_read_only_evidence(self, fetch):
        result = probe(IDENTITY.copy())
        self.assertEqual(result["identity"], IDENTITY)
        self.assertFalse(result["trusted_receipt"])
        self.assertFalse(result["completion_authorized"])
        fetch.assert_called_once()

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run")
    def test_forged_receipt_rejected_before_api_fetch(self, fetch):
        with self.assertRaises(ValueError):
            probe({**IDENTITY, "claim_id": "forged"})
        fetch.assert_not_called()

    @patch("tools.autonomous_receipt_evidence_probe.fetch_protected_run",
           return_value={**RUN, "head_sha": "d" * 40})
    def test_wrong_protected_run_sha_rejected(self, fetch):
        with self.assertRaises(ValueError):
            probe(IDENTITY.copy())


if __name__ == "__main__":
    unittest.main()
