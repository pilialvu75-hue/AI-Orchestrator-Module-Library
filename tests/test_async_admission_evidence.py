"""Regression tests for the async three-stage evidence gate (no certification)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_next_async_admission import verify


class AsyncAdmissionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.upstream = dict(package="async", source_commit="a" * 40,
                             upstream_pub_get="PASS", upstream_analyze="PASS",
                             upstream_test="PASS", admission_authorized=False,
                             certification_authorized=False)
        self.consumer = dict(package="async", source_commit="a" * 40,
                             independent_consumer="BEHAVIOR_PASS",
                             behavior_tested=True, admission_authorized=False,
                             certification_authorized=False)
        self.adapter = dict(package="async", source_commit="a" * 40,
                            status="PACKAGED_CONSUMER_PASS",
                            admission_authorized=False,
                            certification_authorized=False)

    def test_valid_evidence_is_only_review_eligible(self):
        result = verify(self.upstream, self.consumer, self.adapter)
        self.assertTrue(result["eligible_for_tested_intake_review"])
        self.assertFalse(result["admission_authorized"])
        self.assertFalse(result["certification_authorized"])

    def test_rejects_mismatched_pinned_revision(self):
        self.adapter["source_commit"] = "b" * 40
        with self.assertRaises(ValueError):
            verify(self.upstream, self.consumer, self.adapter)

    def test_rejects_missing_upstream_test(self):
        self.upstream["upstream_test"] = "NOT_RUN"
        with self.assertRaises(ValueError):
            verify(self.upstream, self.consumer, self.adapter)

    def test_rejects_import_only_consumer(self):
        self.consumer["behavior_tested"] = False
        with self.assertRaises(ValueError):
            verify(self.upstream, self.consumer, self.adapter)

    def test_rejects_untested_adapter(self):
        self.adapter["status"] = "BUILT_NOT_TESTED"
        with self.assertRaises(ValueError):
            verify(self.upstream, self.consumer, self.adapter)

    def test_rejects_self_authorized_admission(self):
        self.adapter["admission_authorized"] = True
        with self.assertRaises(ValueError):
            verify(self.upstream, self.consumer, self.adapter)

    def test_rejects_self_certification(self):
        self.consumer["certification_authorized"] = True
        with self.assertRaises(ValueError):
            verify(self.upstream, self.consumer, self.adapter)


if __name__ == "__main__":
    unittest.main()
