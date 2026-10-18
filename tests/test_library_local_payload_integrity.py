"""Local code can be certified only if the identical pinned bytes are tested."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_pipeline import (  # noqa: E402
    PipelineError, payload_tree_sha256, validate_payload,
)


class LocalPayloadIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "intake" / "demo.test" / "0.1.0"
        self.source = self.base / "payload" / "src"
        self.source.mkdir(parents=True)
        (self.source / "lib").mkdir()
        (self.source / "lib" / "hello.dart").write_text(
            "String hello() => 'hello';\n", encoding="utf-8"
        )
        self.manifest = {
            "payload": {
                "type": "repository_path",
                "path": "payload/src",
                "sha256": payload_tree_sha256(self.source),
            },
        }

    def test_exact_bytes_pass_and_hash_is_deterministic(self):
        expected = self.manifest["payload"]["sha256"]
        self.assertRegex(expected, r"^[a-f0-9]{64}$")
        self.assertEqual(payload_tree_sha256(self.source), expected)
        validate_payload(self.manifest, self.base)
        self.assertEqual(payload_tree_sha256(self.source), expected)

    def test_mutated_contents_rejected_even_when_path_unchanged(self):
        (self.source / "lib" / "hello.dart").write_text(
            "String hello() => 'changed';\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(PipelineError, "SHA256 mismatch"):
            validate_payload(self.manifest, self.base)

    def test_added_or_renamed_file_rejected(self):
        extra = self.source / "added.dart"
        extra.write_text("const x = 5;\n")
        with self.assertRaisesRegex(PipelineError, "SHA256 mismatch"):
            validate_payload(self.manifest, self.base)
        extra.unlink()
        (self.source / "lib" / "hello.dart").rename(
            self.source / "lib" / "renamed.dart"
        )
        with self.assertRaisesRegex(PipelineError, "SHA256 mismatch"):
            validate_payload(self.manifest, self.base)

    def test_missing_or_invalid_digest_rejected(self):
        for digest in (None, "", "not-a-sha256", "f" * 63):
            with self.subTest(digest=digest):
                self.manifest["payload"]["sha256"] = digest
                with self.assertRaisesRegex(PipelineError, "requires a SHA256"):
                    validate_payload(self.manifest, self.base)

    def test_symlink_nested_payload_forbidden(self):
        (self.source / "link").symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(PipelineError, "symlinks"):
            validate_payload(self.manifest, self.base)

    def test_bounded_number_of_files(self):
        for index in range(513):
            (self.source / f"{index:04d}.dart").write_text("x")
        with self.assertRaisesRegex(PipelineError, "file count limit"):
            payload_tree_sha256(self.source)

    def test_bounded_file_bytes(self):
        huge = self.source / "oversized.bin"
        huge.write_bytes(b"0" * (2 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(PipelineError, "oversized file"):
            payload_tree_sha256(self.source)

    def test_empty_tree_and_directory_symlink_forbidden(self):
        for p in self.source.rglob("*"):
            if p.is_file():
                p.unlink()
        (self.source / "lib").rmdir()
        with self.assertRaisesRegex(PipelineError, "at least one file"):
            payload_tree_sha256(self.source)
        replacement = self.base / "empty"
        replacement.mkdir()
        self.source.rmdir()
        self.source.symlink_to(replacement, target_is_directory=True)
        with self.assertRaisesRegex(PipelineError, "non-symlink"):
            payload_tree_sha256(self.source)


if __name__ == "__main__":
    unittest.main()
