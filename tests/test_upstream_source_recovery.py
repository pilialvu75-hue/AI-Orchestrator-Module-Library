"""Regression coverage for unattended pinned-source acquisition without execution."""
import io
import json
import os
import shutil
import subprocess
from unittest import mock
from urllib.error import HTTPError
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import recover_upstream_snapshots as recovery  # noqa: E402
from library_pipeline import validate_payload  # noqa: E402


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "source"
        self.upstream.mkdir()
        subprocess.run(["git", "init", "-q", str(self.upstream)], check=True)
        subprocess.run(["git", "-C", str(self.upstream), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.upstream), "config", "user.name", "Test"], check=True)
        self.license = b"MIT License\n\nPermission is hereby granted, free of charge\n"
        (self.upstream / "LICENSE").write_bytes(self.license)
        (self.upstream / "module.py").write_bytes(b"def ping():\n    return 'ready'\n")
        self.asset = self.root / "intake" / "diagnostics.logging.example" / "0.1.0"
        self.asset.mkdir(parents=True)
        (self.asset / "provenance").mkdir()
        (self.asset / "provenance" / "LICENSE").write_bytes(self.license)

    def commit(self):
        subprocess.run(["git", "-C", str(self.upstream), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.upstream), "commit", "-qm", "fixture"], check=True)
        sha = subprocess.check_output(
            ["git", "-C", str(self.upstream), "rev-parse", "HEAD"], text=True
        ).strip()
        self.manifest = {
            "id": "diagnostics.logging.example", "version": "0.1.0",
            "status": "discovered", "languages": ["swift"],
            "payload": {
                "type": "upstream_reference",
                "upstream_repository": "https://github.com/example/project",
                "upstream_commit": sha,
            },
            "provenance": {
                "origin": "researcher",
                "source_repository": "https://github.com/example/project",
                "source_commit": sha, "license": "MIT",
                "license_file": "provenance/LICENSE",
            },
            "validation": {"tests_passed": False},
            "security": {"reviewed": False},
        }
        (self.asset / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_acquires_exact_git_objects_and_never_certifies(self):
        self.commit()
        selected = recovery.eligible_intakes(self.root)
        self.assertEqual([self.asset / "manifest.json"], selected)
        result = recovery.acquire(selected[0], test_remote=str(self.upstream))
        self.assertTrue(result["license_bytes_matched"])
        self.assertFalse(result["certification_authorized"])
        self.assertFalse(result["executed_upstream_code"])
        data = json.loads((self.asset / "manifest.json").read_text())
        self.assertEqual("discovered", data["status"])
        self.assertFalse(data["validation"]["tests_passed"])
        self.assertFalse(data["security"]["reviewed"])
        self.assertEqual("upstream_reference", data["payload"]["type"])
        self.assertEqual((self.upstream / "module.py").read_bytes(), (self.asset / "payload/module.py").read_bytes())
        validate_payload(data, self.asset)
        self.assertEqual([], recovery.eligible_intakes(self.root))
        self.assertEqual(result["payload_sha256"], data["payload"]["sha256"])

    def test_refuses_modified_license_without_touching_manifest(self):
        self.commit()
        (self.asset / "provenance/LICENSE").write_bytes(b"unrelated text")
        with self.assertRaisesRegex(recovery.SourceRecoveryError, "license bytes differ"):
            recovery.acquire(self.asset / "manifest.json", test_remote=str(self.upstream))
        self.assertFalse((self.asset / "payload").exists())
        self.assertEqual(self.manifest, json.loads((self.asset / "manifest.json").read_text()))

    def test_refuses_symlink_and_unknown_git_object_types(self):
        (self.upstream / "external").symlink_to("/etc/passwd")
        self.commit()
        with self.assertRaisesRegex(recovery.SourceRecoveryError, "symlink"):
            recovery.acquire(self.asset / "manifest.json", test_remote=str(self.upstream))
        self.assertFalse((self.asset / "payload").exists())

    def test_rejects_unverified_license_and_changed_payload_digest(self):
        self.commit()
        self.manifest["provenance"]["license"] = "NOASSERTION"
        (self.asset / "manifest.json").write_text(json.dumps(self.manifest))
        self.assertEqual([], recovery.eligible_intakes(self.root))
        self.manifest["provenance"]["license"] = "MIT"
        (self.asset / "manifest.json").write_text(json.dumps(self.manifest))
        recovery.acquire(self.asset / "manifest.json", test_remote=str(self.upstream))
        (self.asset / "payload/module.py").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "SHA256 mismatch"):
            validate_payload(json.loads((self.asset / "manifest.json").read_text()), self.asset)


    def test_visibility_probe_is_anonymous_public_only_and_cached(self):
        self.commit()
        recovery.public_repository_state.cache_clear()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = json.dumps({
            "full_name": "example/project", "private": False,
        }).encode("utf-8")
        with mock.patch.object(recovery.url_request, "urlopen") as fetch:
            fetch.return_value.__enter__.return_value = fake_response
            self.assertTrue(recovery.public_repository_state("https://github.com/example/project"))
            self.assertTrue(recovery.public_repository_state("https://github.com/example/project"))
            fetch.assert_called_once()
            request = fetch.call_args.args[0]
            self.assertEqual("https://api.github.com/repos/example/project", request.full_url)
            self.assertNotIn("Authorization", request.headers)
        recovery.public_repository_state.cache_clear()

    def test_private_or_missing_repository_is_never_exportable(self):
        self.commit()
        recovery.public_repository_state.cache_clear()
        private = mock.MagicMock()
        private.read.return_value = json.dumps({
            "full_name": "example/project", "private": True,
        }).encode("utf-8")
        with mock.patch.object(recovery.url_request, "urlopen") as fetch:
            fetch.return_value.__enter__.return_value = private
            self.assertFalse(recovery.public_repository_state("https://github.com/example/project"))
        recovery.public_repository_state.cache_clear()
        with mock.patch.object(recovery.url_request, "urlopen", side_effect=HTTPError(
                "https://api.github.com/repos/example/project", 404,
                "Not Found", {}, io.BytesIO(b""))) as fetch:
            self.assertFalse(recovery.public_repository_state("https://github.com/example/project"))
            fetch.assert_called_once()
        recovery.public_repository_state.cache_clear()
        with mock.patch.object(recovery.url_request, "urlopen", side_effect=HTTPError(
                "https://api.github.com/repos/example/project", 403,
                "Forbidden", {}, io.BytesIO(b""))):
            with self.assertRaisesRegex(recovery.SourceRecoveryError, "status 403"):
                recovery.public_repository_state("https://github.com/example/project")
        recovery.public_repository_state.cache_clear()

    def test_acquire_refuses_private_source_even_with_known_git_commit(self):
        self.commit()
        before = (self.asset / "manifest.json").read_bytes()
        with mock.patch.object(recovery, "public_repository_state", return_value=False):
            with self.assertRaisesRegex(recovery.SourceRecoveryError, "not publicly readable"):
                recovery.acquire(self.asset / "manifest.json")
        self.assertEqual(before, (self.asset / "manifest.json").read_bytes())
        self.assertFalse((self.asset / "payload").exists())

    def test_main_defers_nonpublic_source_and_advances_to_public_candidate(self):
        self.commit()
        second = self.root / "intake" / "diagnostics.logging.public" / "0.1.0"
        shutil.copytree(self.asset, second)
        new_file = second / "manifest.json"
        updated = json.loads(new_file.read_text(encoding="utf-8"))
        updated["id"] = "diagnostics.logging.public"
        updated["provenance"]["source_repository"] = "https://github.com/example/public"
        updated["payload"]["upstream_repository"] = "https://github.com/example/public"
        new_file.write_text(json.dumps(updated), encoding="utf-8")
        output = self.root / "result.json"
        with mock.patch.object(recovery, "public_repository_state",
                               side_effect=lambda repo: repo.endswith("/public")) as visibility, \
             mock.patch.object(recovery, "acquire", return_value={
                 "asset_id": updated["id"], "certification_authorized": False,
             }) as acquire, \
             mock.patch.object(sys, "argv", [
                 "recover_upstream_snapshots.py", "--root", str(self.root),
                 "--output", str(output),
             ]):
            self.assertEqual(0, recovery.main())
        self.assertEqual([mock.call("https://github.com/example/project"),
                          mock.call("https://github.com/example/public")],
                         visibility.call_args_list)
        acquire.assert_called_once_with(new_file)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["acquired"])
        self.assertFalse(report["certification_authorized"])
        self.assertEqual(2, report["eligible_count"])
        self.assertEqual(["diagnostics.logging.example@0.1.0"],
                         report["deferred_nonpublic"])


if __name__ == "__main__":
    unittest.main()
