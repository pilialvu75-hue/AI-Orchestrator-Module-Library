"""Offline safety regressions for Cantiere's experimental Library importer."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tool"))
from cantiere_library_sandbox_preview import verify_preview, PreviewError

PIN = "release.update_manager.firstparty.mia@0.1.0"


def fixture():
    files = [
        {"source_path": "payload/src/package.json", "target_path": "package.json",
         "content": '{"type":"module"}\n'},
        {"source_path": "payload/src/services/main.js", "target_path": "services/main.js",
         "content": "export const ok = true;\n"},
    ]
    digest = hashlib.sha256()
    for entry in sorted(files, key=lambda f: f["target_path"]):
        name = entry["target_path"].encode()
        data = entry["content"].encode()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(hashlib.sha256(data).digest())
    pkg = {
        "schema": "ai-orchestrator.library-module-package.v1",
        "pin": PIN, "asset_id": "release.update_manager.firstparty.mia",
        "version": "0.1.0", "tier": "sandbox_preview", "status": "tested",
        "certified": False, "availability": "experimental",
        "usage_policy": "internal-isolated-evaluation-only",
        "targets": ["linux"], "review": {"production_approved": False},
        "requirements": [
            {"kind": "dependency", "description": "Node.js >=20", "required": True},
            {"kind": "distributionRestriction", "description": "sandbox only",
             "required": True},
        ],
        "integrity": {"payload_sha256": digest.hexdigest()},
        "files": files,
    }
    package_sha = hashlib.sha256(json.dumps(
        pkg, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()
    env = {
        "schema": "ai-orchestrator.library-module-package-envelope.v1",
        "package": pkg, "package_sha256": package_sha,
    }
    index = {
        "schema": "ai-orchestrator.library-experimental-index.v1",
        "policy": "internal-isolated-evaluation-only", "certified": False,
        "packages": [{
            "pin": PIN, "tier": "sandbox_preview",
            "production_approved": False,
            "path": "packages/experimental/release.update_manager.firstparty.mia/0.1.0/package.json",
            "package_sha256": package_sha,
        }],
    }
    return index, env


class CantiereExperimentalImportTests(unittest.TestCase):
    def test_real_payload_content_is_checked_before_staging(self):
        index, env = fixture()
        files = verify_preview(index, env, PIN)
        self.assertEqual(files["services/main.js"], b"export const ok = true;\n")

    def test_tampered_envelope_rejected(self):
        index, env = fixture()
        env["package"]["files"][1]["content"] = "export const ok = false;"
        with self.assertRaisesRegex(PreviewError, "package digest mismatch"):
            verify_preview(index, env, PIN)

    def test_index_cannot_self_approve_production_execution(self):
        index, env = fixture()
        env["package"]["certified"] = True
        index["packages"][0]["package_sha256"] = env["package_sha256"] = hashlib.sha256(
            json.dumps(env["package"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(PreviewError, "restricted to sandbox"):
            verify_preview(index, env, PIN)

    def test_duplicate_or_parent_escape_target_fails(self):
        for target, error in [
            ("../secrets.txt", "unsafe package file path"),
            ("services/../../x.js", "unsafe package file path"),
            ("package.json", "duplicate module file path"),
        ]:
            with self.subTest(target=target):
                index, env = fixture()
                env["package"]["files"][1]["target_path"] = target
                sha = hashlib.sha256(json.dumps(
                    env["package"], sort_keys=True, separators=(",", ":")
                ).encode()).hexdigest()
                index["packages"][0]["package_sha256"] = env["package_sha256"] = sha
                with self.assertRaisesRegex(PreviewError, error):
                    verify_preview(index, env, PIN)

    def test_dependency_and_platform_must_be_declared(self):
        for change, expected in [
            ("targets", "Linux was not validated"),
            ("requirements", "Node.js runtime dependency not declared"),
        ]:
            with self.subTest(change=change):
                index, env = fixture()
                if change == "targets":
                    env["package"]["targets"] = ["android"]
                else:
                    env["package"]["requirements"] = env["package"]["requirements"][1:]
                sha = hashlib.sha256(json.dumps(
                    env["package"], sort_keys=True, separators=(",", ":")
                ).encode()).hexdigest()
                index["packages"][0]["package_sha256"] = env["package_sha256"] = sha
                with self.assertRaisesRegex(PreviewError, expected):
                    verify_preview(index, env, PIN)


if __name__ == "__main__":
    unittest.main()
