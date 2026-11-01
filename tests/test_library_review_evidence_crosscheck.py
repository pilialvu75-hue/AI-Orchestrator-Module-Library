"""Offline fail-closed tests for review/OSV evidence binding."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_review_evidence_crosscheck import digest, verify


def packet():
    item = {"asset_id": "utility.fixnum.external.dartlang.fixnum",
            "status": "INDEPENDENT_REVIEW_REQUIRED", "security_reviewed": False,
            "source": {"payload_tree_sha256": "a" * 64},
            "dependency_inventory": {"cyclonedx_sbom": {"components": [
                {"purl": "pkg:pub/fixnum@1.1.1"},
                {"bom-ref": "pkg:generic/aivexus_external_fixnum@0.1.0"}]}}}
    report = {"asset_id": item["asset_id"], "security_reviewed": False,
              "certification_authorized": False, "review_request_sha256": digest(item),
              "sbom_sha256": digest(item["dependency_inventory"]["cyclonedx_sbom"]),
              "source_payload_sha256": "a" * 64, "advisory_scan_completed": True,
              "provider": "OSV", "packages": [
                  {"purl": "pkg:pub/fixnum@1.1.1", "vulnerability_ids": []}],
              "vulnerabilities_found": 0}
    return ({"requests": [item], "count": 1, "certification_authorized": False},
            {"reports": [report], "count": 1, "certification_authorized": False})


class EvidenceTests(unittest.TestCase):
    def test_exact_packet(self):
        self.assertEqual(verify(*packet()), 1)

    def test_malformed_vulnerability_inventory_rejected(self):
        for malformed in (None, "not-a-list", 7):
            requests, evidence = copy.deepcopy(packet())
            evidence["reports"][0]["packages"][0]["vulnerability_ids"] = malformed
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                verify(requests, evidence)

    def test_tampering_fails_closed(self):
        for mutation in ("source", "sbom", "request", "coverage", "count", "approval"):
            requests, evidence = copy.deepcopy(packet())
            if mutation == "source":
                evidence["reports"][0]["source_payload_sha256"] = "b" * 64
            elif mutation == "sbom":
                evidence["reports"][0]["sbom_sha256"] = "b" * 64
            elif mutation == "request":
                evidence["reports"][0]["review_request_sha256"] = "b" * 64
            elif mutation == "coverage":
                evidence["reports"][0]["packages"] = []
            elif mutation == "count":
                evidence["reports"][0]["vulnerabilities_found"] = 1
            else:
                evidence["reports"][0]["certification_authorized"] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify(requests, evidence)


if __name__ == "__main__":
    unittest.main()
