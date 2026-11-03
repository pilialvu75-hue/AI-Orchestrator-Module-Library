"""Offline tests for source-bound independent Dart audit."""
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_independent_dart_static_audit import audit


class StaticAuditTests(unittest.TestCase):
    def test_nested_symlink_cannot_escape_source_inventory(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "intake" / "test.module" / "0.1.0" / "payload" / "src"
            base.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            data = b"void main() {}\n"
            (outside / "sample.dart").write_bytes(data)
            (base / "nested").symlink_to(outside, target_is_directory=True)
            request = {"asset_id": "test.module", "version": "0.1.0",
                       "source": {"payload_tree_sha256": "a" * 64,
                                  "all_file_digests": [{"path": "nested/sample.dart",
                                  "sha256": hashlib.sha256(data).hexdigest(),
                                  "bytes": len(data)}]}}
            with self.assertRaisesRegex(ValueError, "traverses symlink"):
                audit(root, request)

    def test_unlisted_source_file_fails_closed(self):
        with TemporaryDirectory() as temp:
            base = Path(temp) / "intake" / "test.module" / "0.1.0" / "payload" / "src"
            base.mkdir(parents=True)
            data = b"void main() {}\\n"
            (base / "listed.dart").write_bytes(data)
            (base / "hidden.dart").write_text("import 'dart:io';\\n")
            request = {"asset_id": "test.module", "version": "0.1.0",
                       "source": {"payload_tree_sha256": "a" * 64,
                                  "all_file_digests": [{"path": "listed.dart",
                                  "sha256": hashlib.sha256(data).hexdigest(),
                                  "bytes": len(data)}]}}
            with self.assertRaisesRegex(ValueError, "exact source tree"):
                audit(Path(temp), request)
            (base / "hidden.dart").unlink()
            request["source"]["all_file_digests"].append(dict(request["source"]["all_file_digests"][0]))
            with self.assertRaisesRegex(ValueError, "duplicate source inventory"):
                audit(Path(temp), request)

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
