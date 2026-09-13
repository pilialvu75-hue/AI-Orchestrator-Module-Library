from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_package import PackageError, build_package  # noqa: E402


class LibraryPackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write_json(
            self.root / "contracts" / "index.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-13T19:00:00Z",
                "contracts": [
                    {
                        "capability_id": "demo.capability",
                        "contract_id": "demo.capability.v1",
                        "contract_version": "1.0",
                        "status": "stable",
                        "description": "fixture",
                        "replacement": None,
                    }
                ],
            },
        )
        self.write_json(
            self.root / "catalog" / "needs.json",
            {"schema_version": 1, "updated_at": "2026-09-13T19:00:00Z", "items": []},
        )
        self.write_json(
            self.root / "catalog" / "lifecycle.json",
            {"schema_version": 1, "revision": 0, "updated_at": "2026-09-13T19:00:00Z", "events": []},
        )
        self.assets: list[dict] = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def finalize_catalog(self) -> None:
        self.write_json(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "package-test",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-13T19:00:00Z",
                "assets": self.assets,
            },
        )

    def add_asset(
        self,
        asset_id: str,
        *,
        availability: str = "active",
        payload_type: str = "archive",
    ) -> None:
        version = "1.0.0"
        base = self.root / "modules" / asset_id / version
        payload: dict
        if payload_type == "archive":
            payload_document = {
                "schema": "ai-orchestrator.library-intake-payload.v1",
                "files": [
                    {
                        "path": "lib/demo.dart",
                        "content_base64": base64.b64encode(b"class Demo {}\n").decode("ascii"),
                    }
                ],
            }
            payload_json = json.dumps(payload_document, separators=(",", ":"), ensure_ascii=False)
            archive = base / "payload" / "library-intake-payload.json"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(payload_json, encoding="utf-8")
            payload = {
                "type": "archive",
                "path": "payload/library-intake-payload.json",
                "sha256": hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                "upstream_repository": None,
                "upstream_commit": None,
            }
        elif payload_type == "upstream_reference":
            payload = {
                "type": "upstream_reference",
                "path": None,
                "sha256": None,
                "upstream_repository": "https://github.com/example/demo",
                "upstream_commit": "0123456789abcdef0123456789abcdef01234567",
            }
        else:
            source = base / "payload" / "src"
            source.mkdir(parents=True, exist_ok=True)
            (source / "demo.dart").write_text("class Demo {}\n", encoding="utf-8")
            payload = {
                "type": "repository_path",
                "path": "payload/src",
                "sha256": None,
                "upstream_repository": None,
                "upstream_commit": None,
            }

        manifest = {
            "id": asset_id,
            "name": "Demo",
            "version": version,
            "kind": "module",
            "status": "certified",
            "description": "fixture",
            "tags": [],
            "capabilities": ["demo.capability"],
            "platforms": ["android"],
            "languages": ["dart"],
            "frameworks": ["flutter"],
            "entry_paths": ["lib/demo.dart"],
            "dependencies": [{"name": "demo_dep", "version": "^1.0.0", "source": "pub"}],
            "provenance": {
                "origin": "cantiere",
                "source_repository": None,
                "source_commit": None,
                "source_tag": None,
                "source_project_id": "fixture",
                "source_task_id": None,
                "license": "MIT",
                "license_file": None,
                "retrieved_at": "2026-09-13T19:00:00Z",
            },
            "validation": {
                "score": 0.95,
                "tests_passed": True,
                "test_report": None,
                "validated_at": "2026-09-13T19:00:00Z",
                "validated_on": ["android"],
            },
            "security": {
                "reviewed": True,
                "reviewed_at": "2026-09-13T19:00:00Z",
                "known_vulnerabilities": 0,
                "sbom": None,
                "notes": None,
            },
            "integration": {
                "estimated_effort": "low",
                "adaptation_allowed": True,
                "known_constraints": ["Check host configuration"],
                "adapter_notes": None,
            },
            "connector": {
                "standard": "ai-orchestrator-lego",
                "standard_version": "1.0.0",
                "provides": [
                    {
                        "capability_id": "demo.capability",
                        "contract_id": "demo.capability.v1",
                        "contract_version": "1.0",
                    }
                ],
                "requires": [],
                "integration_mode": "source_bundle",
                "adapters": [],
                "configuration_schema": None,
                "healthcheck": {"type": "none", "path": None},
            },
            "payload": payload,
        }
        manifest_path = base / "manifest.json"
        self.write_json(manifest_path, manifest)
        self.assets.append(
            {
                "id": asset_id,
                "version": version,
                "manifest": manifest_path.relative_to(self.root).as_posix(),
                "status": "certified",
                "availability": availability,
                "kind": "module",
                "capabilities": ["demo.capability"],
                "platforms": ["android"],
                "contracts": ["demo.capability.v1"],
            }
        )

    def test_exports_canonical_archive_as_assembler_ready_text_file(self) -> None:
        self.add_asset("demo.archive")
        self.finalize_catalog()
        envelope = build_package(self.root, "demo.archive", "1.0.0")
        package = envelope["package"]
        self.assertEqual("ai-orchestrator.library-module-package.v1", package["schema"])
        self.assertEqual("demo.archive@1.0.0", package["pin"])
        self.assertEqual("lib/demo.dart", package["files"][0]["target_path"])
        self.assertEqual("class Demo {}\n", package["files"][0]["content"])
        self.assertEqual(["demo.capability.v1"], package["contracts"])
        self.assertRegex(package["integrity"]["module_tree_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(envelope["package_sha256"], r"^[a-f0-9]{64}$")

    def test_repository_path_payload_exports_relative_files(self) -> None:
        self.add_asset("demo.repository", payload_type="repository_path")
        self.finalize_catalog()
        package = build_package(self.root, "demo.repository", "1.0.0")["package"]
        self.assertEqual("demo.dart", package["files"][0]["target_path"])
        self.assertEqual("payload/src/demo.dart", package["files"][0]["source_path"])

    def test_upstream_reference_is_fail_explicit_not_fake_source(self) -> None:
        self.add_asset("demo.upstream", payload_type="upstream_reference")
        self.finalize_catalog()
        package = build_package(self.root, "demo.upstream", "1.0.0")["package"]
        self.assertEqual([], package["files"])
        manual = [item for item in package["requirements"] if item["kind"] == "manualReview" and item["required"]]
        self.assertTrue(any("0123456789abcdef" in item["description"] for item in manual))

    def test_revoked_is_never_exported_and_deprecated_requires_opt_in(self) -> None:
        self.add_asset("demo.revoked", availability="revoked")
        self.add_asset("demo.deprecated", availability="deprecated")
        self.finalize_catalog()
        with self.assertRaisesRegex(PackageError, "revoked"):
            build_package(self.root, "demo.revoked", "1.0.0")
        with self.assertRaisesRegex(PackageError, "deprecated"):
            build_package(self.root, "demo.deprecated", "1.0.0")
        package = build_package(
            self.root,
            "demo.deprecated",
            "1.0.0",
            include_deprecated=True,
        )["package"]
        self.assertEqual("deprecated", package["availability"])


if __name__ == "__main__":
    unittest.main()
