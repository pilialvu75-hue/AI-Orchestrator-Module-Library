"""Offline tests for live OSV evidence; no external network required."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from tempfile import TemporaryDirectory
# unittest discovery does not automatically add the repository's tools/ path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from autonomous_public_dart_osv_scan import main, scan  # noqa: E402


def request():
    return {
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "asset_id": "utility.fixnum.external.dartlang.fixnum",
        "source": {"payload_tree_sha256": "a" * 64},
        "dependency_inventory": {"cyclonedx_sbom": {"components": [
            {"purl": "pkg:pub/fixnum@1.1.1", "name": "fixnum", "version": "1.1.1"},
            {"name": "local-adapter", "purl": "pkg:generic/aivexus_external_fixnum@0.1.0"},
        ]}},
    }


class ScanTests(unittest.TestCase):
    def test_clean_advisory_scan_never_certifies(self):
        class Response(BytesIO):
            pass
        with patch("autonomous_public_dart_osv_scan.urllib.request.urlopen",
                   return_value=Response(b"{}")) as urlopen:
            result = scan(request())
        self.assertEqual(result["packages"][0]["package"], "fixnum")
        self.assertTrue(result["advisory_scan_completed"])
        self.assertEqual(result["vulnerabilities_found"], 0)
        self.assertFalse(result["security_reviewed"])
        self.assertFalse(result["certification_authorized"])
        args, kwargs = urlopen.call_args
        self.assertEqual(args[0].full_url, "https://api.osv.dev/v1/query")
        self.assertEqual(json.loads(args[0].data)["package"]["ecosystem"], "Pub")

    def test_known_advisories_are_preserved(self):
        with patch("autonomous_public_dart_osv_scan.urllib.request.urlopen",
                   return_value=BytesIO(b'{"vulns":[{"id":"GHSA-example"}]}')):
            result = scan(request())
        self.assertEqual(result["vulnerabilities_found"], 1)
        self.assertEqual(result["packages"][0]["vulnerability_ids"], ["GHSA-example"])
        self.assertFalse(result["certification_authorized"])

    def test_malformed_osv_response_fails_closed(self):
        for response in (b'[]', b'{"vulns":{}}', b'{"vulns":[{}]}'):
            with self.subTest(response=response):
                with patch('autonomous_public_dart_osv_scan.urllib.request.urlopen',
                           return_value=BytesIO(response)):
                    with self.assertRaisesRegex(ValueError, 'invalid OSV'):
                        scan(request())

    def test_sbom_identity_mismatch_fails_closed(self):
        for change in ({"name": "other"}, {"version": "9.9.9"}, {"purl": "pkg:pub/fixnum"}):
            with self.subTest(change=change):
                item = request()
                item["dependency_inventory"]["cyclonedx_sbom"]["components"][0].update(change)
                with self.assertRaises(ValueError):
                    scan(item)

    def test_generated_local_adapter_bom_ref_is_accepted(self):
        item = request()
        item["dependency_inventory"]["cyclonedx_sbom"]["components"][1] = {
            "type": "library",
            "bom-ref": "pkg:generic/aivexus_external_fixnum@0.1.0",
            "name": "aivexus_external_fixnum",
            "version": "0.1.0",
        }
        with patch("autonomous_public_dart_osv_scan.urllib.request.urlopen",
                   return_value=BytesIO(b"{}")):
            result = scan(item)
        self.assertEqual(len(result["packages"]), 1)
        self.assertFalse(result["certification_authorized"])

    def test_unknown_or_duplicate_sbom_component_fails_closed(self):
        for purl in (None, "pkg:npm/unreviewed@1.0", "pkg:pub/fixnum@1.1.1"):
            with self.subTest(purl=purl):
                item = request()
                item["dependency_inventory"]["cyclonedx_sbom"]["components"].append(
                    {"name": "unreviewed", "version": "1.0", "purl": purl})
                with self.assertRaises(ValueError):
                    scan(item)

    def test_forged_or_duplicate_local_adapter_fails_closed(self):
        for extra in (
            {"purl": "pkg:generic/aivexus_external_fake@1.0",
             "name": "different", "version": "1.0"},
            {"purl": "pkg:generic/aivexus_external_fake@1.0",
             "name": "aivexus_external_fake", "version": "2.0"},
            {"purl": "pkg:generic/aivexus_external_fake@1.0",
             "name": "aivexus_external_fake", "version": "1.0"},
        ):
            item = request()
            item["dependency_inventory"]["cyclonedx_sbom"]["components"][1] = {
                "bom-ref": "pkg:generic/aivexus_external_fixnum@0.1.0",
                "name": "aivexus_external_fixnum", "version": "0.1.0"}
            item["dependency_inventory"]["cyclonedx_sbom"]["components"].append(extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                scan(item)

    def test_network_failure_fails_closed(self):
        with patch("autonomous_public_dart_osv_scan.urllib.request.urlopen",
                   side_effect=TimeoutError("OSV unavailable")):
            with self.assertRaises(TimeoutError):
                scan(request())

    def test_no_upstream_package_fails_closed(self):
        item = request()
        item["dependency_inventory"]["cyclonedx_sbom"]["components"] = []
        with self.assertRaises(ValueError):
            scan(item)

    def test_empty_review_collection_fails_closed(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / 'requests.json'
            target = Path(folder) / 'osv.json'
            source.write_text(json.dumps({'requests': []}))
            with patch('sys.argv', ['scan', '--requests', str(source), '--output', str(target)]):
                with self.assertRaisesRegex(ValueError, 'no independent review requests'):
                    main()
            self.assertFalse(target.exists())

    def test_unapproved_request_fails_closed(self):
        item = request()
        item["status"] = "CERTIFIED"
        with self.assertRaises(ValueError):
            scan(item)


if __name__ == "__main__":
    unittest.main()
