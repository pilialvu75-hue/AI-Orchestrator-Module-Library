"""Offline policy regression tests. Synthetic OSV receipts are NOT approvals."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from autonomous_public_dart_review import collect
from library_independent_dart_static_audit import audit
from library_independent_review_preflight import assess as preflight_assess
from library_fixnum_technical_review import assess, ASSET, PACKAGE
from library_review_evidence_crosscheck import digest


class FixnumTechnicalReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = collect(ROOT)
        cls.static = {
            "schema": "aivexus.library.static-source-audit.v1",
            "items": [audit(ROOT, x) for x in cls.requests["requests"]],
            "security_reviewed": False, "certification_authorized": False,
        }
        cls.now = dt.datetime(2026, 11, 17, 12, 0, tzinfo=dt.timezone.utc)
        reports = []
        for request in cls.requests["requests"]:
            sbom = request["dependency_inventory"]["cyclonedx_sbom"]
            packages = [
                {"purl": c["purl"], "package": c["name"],
                 "version": c["version"], "vulnerability_ids": []}
                for c in sbom["components"] if c.get("purl", "").startswith("pkg:pub/")
            ]
            reports.append({
                "asset_id": request["asset_id"],
                "source_payload_sha256": request["source"]["payload_tree_sha256"],
                "sbom_sha256": digest(sbom),
                "review_request_sha256": digest(request),
                "scanned_at_utc": cls.now.isoformat(),
                "provider": "OSV", "endpoint": "https://api.osv.dev/v1/query",
                "packages": packages,
                "advisory_scan_completed": True, "vulnerabilities_found": 0,
                "security_reviewed": False, "certification_authorized": False,
            })
        cls.evidence = {
            "schema": "aivexus.library.osv-advisory-collection.v1",
            "count": len(reports), "reports": reports,
            "security_reviewed": False, "certification_authorized": False,
        }
        cls.ci = {
            "id": 41015199646,
            "head_sha": "fbc133a50e86536dc9bfb97c524e5b4bdb8a9028",
            "name": "Library isolated verification of Researcher public Dart intake",
            "conclusion": "success", "status": "completed", "event": "pull_request",
        }

    def inputs(self):
        req = copy.deepcopy(self.requests)
        ev = copy.deepcopy(self.evidence)
        st = copy.deepcopy(self.static)
        return req, ev, st, preflight_assess(req, ev, st), copy.deepcopy(self.ci)

    def evaluate(self, req, ev, static, gate, ci, now=None):
        return assess(ROOT, req, ev, static, gate, ci,
                      now=self.now if now is None else now)

    def test_source_bound_technical_proof_is_not_certification(self):
        result = self.evaluate(*self.inputs())
        self.assertTrue(result["technical_evidence_checked"])
        self.assertFalse(result["certification_authorized"])
        self.assertFalse(result["security_reviewed"])
        self.assertFalse(result["production_installable"])
        self.assertEqual(result["open_blockers"], [
            "INDEPENDENT_SOURCE_LICENSE_PRIVACY_REVIEW_REQUIRED",
            "PROTECTED_REVIEWER_SIGNATURE_REQUIRED",
        ])

    def test_unverified_or_mismatched_ci_receipts_fail_closed(self):
        for key, replacement in (("conclusion", "failure"), ("id", 123),
                                 ("head_sha", "f" * 40), ("name", "unrelated")):
            with self.subTest(key=key):
                inputs = list(self.inputs())
                inputs[4][key] = replacement
                with self.assertRaisesRegex(ValueError, "GitHub CI"):
                    self.evaluate(*inputs)

    def test_stale_or_future_advisory_scan_is_rejected(self):
        for delta in (-dt.timedelta(days=2), dt.timedelta(minutes=5)):
            with self.subTest(delta=delta):
                inputs = list(self.inputs())
                for report in inputs[1]["reports"]:
                    report["scanned_at_utc"] = (self.now + delta).isoformat()
                inputs[3] = preflight_assess(inputs[0], inputs[1], inputs[2])
                with self.assertRaisesRegex(ValueError, "stale or from the future"):
                    self.evaluate(*inputs)

    def test_advisory_presence_fails_even_when_crosscheck_matches(self):
        inputs = list(self.inputs())
        rec = next(r for r in inputs[1]["reports"] if r["asset_id"] == ASSET)
        rec["packages"][0]["vulnerability_ids"] = ["OSV-TEST-ADVISORY"]
        rec["vulnerabilities_found"] = 1
        inputs[3] = preflight_assess(inputs[0], inputs[1], inputs[2])
        with self.assertRaises(ValueError):
            self.evaluate(*inputs)

    def test_findings_cannot_be_relabelled_approved(self):
        inputs = list(self.inputs())
        rec = next(r for r in inputs[2]["items"] if r["asset_id"] == ASSET)
        rec["findings"] = [{"file": "lib/x.dart", "rule": "NETWORK_CLIENT"}]
        inputs[3] = preflight_assess(inputs[0], inputs[1], inputs[2])
        with self.assertRaises(ValueError):
            self.evaluate(*inputs)

    def test_forged_source_binding_is_rejected(self):
        inputs = list(self.inputs())
        rec = next(r for r in inputs[0]["requests"] if r["asset_id"] == ASSET)
        rec["source"]["payload_tree_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            self.evaluate(*inputs)

    def test_modified_preflight_cannot_erase_reviewer_requirements(self):
        inputs = list(self.inputs())
        next(r for r in inputs[3]["items"] if r["asset_id"] == ASSET)["reasons"] = []
        with self.assertRaisesRegex(ValueError, "preflight differs"):
            self.evaluate(*inputs)


if __name__ == "__main__":
    unittest.main()
