"""Offline tests for source-bound independent Dart audit."""
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_independent_dart_static_audit import audit


class StaticAuditTests(unittest.TestCase):
    def test_findings_are_not_approval(self):
        with TemporaryDirectory() as temp:
            base = Path(temp) / "intake" / "test.module" / "0.1.0" / "payload" / "src"
            base.mkdir(parents=True)
            data = b"import 'dart:io';\nvoid run() { Process.run('echo', []); }\n"
            (base / "sample.dart").write_bytes(data)
            request = {"asset_id": "test.module", "version": "0.1.0",
                       "source": {"payload_tree_sha256": "a" * 64,
                                  "all_file_digests": [{"path": "sample.dart",
                                  "sha256": hashlib.sha256(data).hexdigest(),
                                  "bytes": len(data)}]}}
            result = audit(Path(temp), request)
            self.assertIn("SENSITIVE_IMPORT", [x["rule"] for x in result["findings"]])
            self.assertFalse(result["certification_authorized"])
            request["source"]["all_file_digests"][0]["sha256"] = "b" * 64
            with self.assertRaises(ValueError):
                audit(Path(temp), request)


if __name__ == "__main__":
    unittest.main()
