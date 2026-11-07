"""Offline tests for review preflight."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_independent_review_preflight import assess
from test_library_review_evidence_crosscheck import packet


class PreflightTests(unittest.TestCase):
    @staticmethod
    def _audit(requests):
        return {'schema': 'aivexus.library.static-source-audit.v1', 'items': [
            {'asset_id': item['asset_id'],
             'source_payload_sha256': item['source']['payload_tree_sha256'],
             'static_scan_completed': True, 'findings': [],
             'security_reviewed': False, 'certification_authorized': False,
             'manual_security_review_required': True}
            for item in requests['requests']],
            'security_reviewed': False, 'certification_authorized': False}

    def test_malformed_static_audit_is_rejected(self):
        requests, evidence = packet()
        for invalid in ([], {"schema": "aivexus.library.static-source-audit.v1", "items": None}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    assess(requests, evidence, invalid)

    def test_non_object_static_audit_item_is_rejected(self):
        requests, evidence = packet()
        audit = {"schema": "aivexus.library.static-source-audit.v1", "items": [None]}
        with self.assertRaisesRegex(ValueError, "static audit item must be an object"):
            assess(requests, evidence, audit)

    def test_duplicate_static_audit_identity_is_rejected(self):
        requests, evidence = packet()
        audit = self._audit(requests)
        audit['items'].append(dict(audit['items'][0]))
        requests['requests'].append(dict(requests['requests'][0], asset_id='second.asset'))
        requests['count'] = 2
        evidence['reports'].append(dict(evidence['reports'][0], asset_id='second.asset'))
        evidence['count'] = 2
        from library_review_evidence_crosscheck import digest
        evidence['reports'][1]['review_request_sha256'] = digest(requests['requests'][1])
        with self.assertRaisesRegex(ValueError, 'duplicate static audit source identity'):
            assess(requests, evidence, audit)

    def test_unsigned_audit_cannot_claim_security_approval(self):
        requests, evidence = packet()
        for field, forged in (('security_reviewed', True), ('certification_authorized', True)):
            with self.subTest(scope='packet', field=field):
                audit = self._audit(requests)
                audit[field] = forged
                with self.assertRaisesRegex(ValueError, 'unsigned static audit'):
                    assess(requests, evidence, audit)
            with self.subTest(scope='item', field=field):
                audit = self._audit(requests)
                audit['items'][0][field] = forged
                with self.assertRaisesRegex(ValueError, 'cannot assert security approval'):
                    assess(requests, evidence, audit)
        audit = self._audit(requests)
        audit['items'][0]['manual_security_review_required'] = False
        with self.assertRaisesRegex(ValueError, 'cannot assert security approval'):
            assess(requests, evidence, audit)

    def test_missing_static_audit_is_rejected(self):
        requests, evidence = packet()
        with self.assertRaisesRegex(ValueError, 'independent static source audit is required'):
            assess(requests, evidence)

    def test_clean_advisories_do_not_approve(self):
        requests, evidence = packet()
        result = assess(requests, evidence, self._audit(requests))
        self.assertEqual(result["items"][0]["decision"], "BLOCKED")
        self.assertFalse(result["certification_authorized"])

    def test_known_advisories_block(self):
        requests, evidence = packet()
        evidence["reports"][0]["packages"][0]["vulnerability_ids"] = ["GHSA-example"]
        evidence["reports"][0]["vulnerabilities_found"] = 1
        result = assess(requests, evidence, self._audit(requests))
        self.assertIn("KNOWN_UPSTREAM_ADVISORIES", result["items"][0]["reasons"])


    def test_missing_source_license_and_ci_evidence_are_explicit_blockers(self):
        requests, evidence = packet()
        result = assess(requests, evidence, self._audit(requests))
        reasons = result["items"][0]["reasons"]
        self.assertIn("SOURCE_FILE_INVENTORY_MISSING", reasons)
        self.assertIn("ORIGINAL_LICENSE_DIGEST_MISSING", reasons)
        self.assertIn("REPRODUCIBLE_CI_IDENTITY_MISSING", reasons)
        self.assertIn("INDEPENDENT_SOURCE_LICENSE_PRIVACY_REVIEW_REQUIRED", reasons)
        self.assertIn("PROTECTED_REVIEWER_SIGNATURE_REQUIRED", reasons)
        self.assertFalse(result["items"][0]["security_reviewed"])
        self.assertFalse(result["items"][0]["certification_authorized"])

    def test_complete_metadata_still_requires_independent_review(self):
        requests, evidence = packet()
        source = requests["requests"][0]["source"]
        source["all_file_digests"] = {"lib/src.dart": "a" * 64}
        source["license_sha256"] = "b" * 64
        requests["requests"][0]["tested_evidence"] = {"ci_run_id": 12345}
        from library_review_evidence_crosscheck import digest
        evidence["reports"][0]["review_request_sha256"] = digest(requests["requests"][0])
        result = assess(requests, evidence, self._audit(requests))
        reasons = result["items"][0]["reasons"]
        self.assertNotIn("SOURCE_FILE_INVENTORY_MISSING", reasons)
        self.assertNotIn("ORIGINAL_LICENSE_DIGEST_MISSING", reasons)
        self.assertNotIn("REPRODUCIBLE_CI_IDENTITY_MISSING", reasons)
        self.assertIn("PROTECTED_REVIEWER_SIGNATURE_REQUIRED", reasons)
        self.assertEqual(result["items"][0]["decision"], "BLOCKED")
        self.assertFalse(result["certification_authorized"])

if __name__ == "__main__":
    unittest.main()
