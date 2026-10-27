"""Regression tests for tiered access to actually tested local-source modules."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from library_experimental import (  # noqa: E402
    preview_package, export_experimental_packages, PREVIEW_POLICY,
)
from library_package import PackageError  # noqa: E402
from library_source_integrity import payload_tree_sha256  # noqa: E402

ASSET = "diagnostics.logging.library.privacy_events"
VERSION = "0.1.0"


class SandboxAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = ROOT / "intake" / ASSET / VERSION
        self.base = self.root / "intake" / ASSET / VERSION
        self.base.parent.mkdir(parents=True)
        shutil.copytree(source, self.base)
        self.manifest_path = self.base / "manifest.json"

    def manifest(self):
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, value):
        self.manifest_path.write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def test_tested_source_is_accessible_in_separate_noncertified_tier(self):
        envelope = preview_package(self.root, ASSET, VERSION)
        package = envelope["package"]
        self.assertEqual(package["tier"], "sandbox_preview")
        self.assertEqual(package["usage_policy"], PREVIEW_POLICY)
        self.assertIs(package["certified"], False)
        self.assertEqual(package["status"], "tested")
        self.assertEqual(package["availability"], "experimental")
        self.assertIs(package["review"]["security_reviewed"], False)
        self.assertIs(package["review"]["license_verified"], False)
        self.assertIs(package["review"]["production_approved"], False)
        self.assertEqual(
            {f["target_path"] for f in package["files"]},
            {"lib/privacy_diagnostic_events.dart",
             "bin/self_test.dart",
             "pubspec.yaml",
             "README.md"},
        )
        self.assertEqual(set(package["targets"]), {"linux", "macos", "windows"})
        self.assertTrue(
            any(rule["kind"] == "distributionRestriction"
                and rule["required"] is True for rule in package["requirements"])
        )
        self.assertEqual(
            package["integrity"]["payload_sha256"],
            self.manifest()["payload"]["sha256"],
        )

    def test_experimental_exports_do_not_modify_certified_catalog(self):
        catalog = self.root / "catalog" / "index.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"assets":[]}')
        original = catalog.read_bytes()
        report = export_experimental_packages(self.root)
        self.assertEqual(report, {"count": 1, "blocked": 0})
        self.assertEqual(catalog.read_bytes(), original)
        preview_index = json.loads(
            (self.root / "packages/experimental-index.json").read_text()
        )
        self.assertIs(preview_index["certified"], False)
        self.assertEqual(len(preview_index["packages"]), 1)
        self.assertIs(preview_index["packages"][0]["production_approved"], False)
        self.assertTrue((self.root / preview_index["packages"][0]["path"]).is_file())
        self.assertFalse((self.root / "packages/index.json").exists())

    def test_unreviewed_source_does_not_need_nonexistent_external_signer_for_sandbox(self):
        manifest = self.manifest()
        self.assertIs(manifest["security"]["reviewed"], False)
        self.assertIsNone(manifest["provenance"]["license"])
        self.assertIsNone(manifest["security"]["review_report"])
        self.assertEqual(
            preview_package(self.root, ASSET, VERSION)["package"]["tier"],
            "sandbox_preview",
        )

    def test_any_changed_source_bytes_or_test_report_blocks_preview(self):
        source = self.base / "payload/src/lib/privacy_diagnostic_events.dart"
        source.write_text(source.read_text() + "\n// tampered\n")
        with self.assertRaisesRegex(PackageError, "source|digest"):
            preview_package(self.root, ASSET, VERSION)
        shutil.copy2(
            ROOT / "intake" / ASSET / VERSION / "payload/src/lib/privacy_diagnostic_events.dart",
            source,
        )
        report = self.base / "tests/dart-cross-platform-ci-report.json"
        data = json.loads(report.read_text())
        data["payload_sha256"] = "f" * 64
        report.write_text(json.dumps(data))
        with self.assertRaisesRegex(PackageError, "evidence|source"):
            preview_package(self.root, ASSET, VERSION)

    def test_discovered_or_upstream_pointer_is_not_executable_source(self):
        manifest = self.manifest()
        for status in ("discovered", "quarantined", "normalized"):
            manifest["status"] = status
            self.write_manifest(manifest)
            with self.subTest(status=status), self.assertRaisesRegex(PackageError, "tested"):
                preview_package(self.root, ASSET, VERSION)
        manifest["status"] = "tested"
        manifest["payload"] = {
            "type": "upstream_reference",
            "upstream_commit": "a" * 40,
            "upstream_repository": "https://github.com/example/pointer",
        }
        self.write_manifest(manifest)
        with self.assertRaises(PackageError):
            preview_package(self.root, ASSET, VERSION)

    def test_researcher_owned_real_source_and_declared_deps_can_be_previewed(self):
        manifest = self.manifest()
        manifest["provenance"]["origin"] = "researcher"
        manifest["provenance"]["source_repository"] = (
            "https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Researcher"
        )
        manifest["dependencies"] = [
            {"name": "dart_package", "version": "^1.0.0", "source": "pub"},
        ]
        self.write_manifest(manifest)
        package = preview_package(self.root, ASSET, VERSION)["package"]
        self.assertEqual(package["tier"], "sandbox_preview")
        self.assertTrue(any(rule["kind"] == "dependency"
                            for rule in package["requirements"]))
        self.assertEqual(
            package["source"]["source_repository"],
            manifest["provenance"]["source_repository"],
        )
        self.assertFalse(package["certified"])

    def test_foreign_repo_or_lookalike_owner_is_excluded(self):
        manifest = self.manifest()
        for source in (
            "https://github.com/outsider/unknown-source",
            "https://github.com/pilialvu75-hue.evil/unknown",
            "https://github.com/pilialvu75-hue/repo/subfolder",
            "",
        ):
            with self.subTest(source=source):
                manifest["provenance"]["source_repository"] = source
                self.write_manifest(manifest)
                with self.assertRaisesRegex(PackageError, "Aivexus-owned"):
                    preview_package(self.root, ASSET, VERSION)

    def test_unsafe_filename_rejected_even_with_matching_source_digest(self):
        source = self.base / "payload/src"
        (source / ".env").write_text("not-a-real-secret")
        manifest = self.manifest()
        manifest["payload"]["sha256"] = payload_tree_sha256(source)
        self.write_manifest(manifest)
        report_path = self.base / manifest["validation"]["test_report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["payload_sha256"] = manifest["payload"]["sha256"]
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(PackageError, "unsafe"):
            preview_package(self.root, ASSET, VERSION)

    def test_cannot_use_preview_for_certified_package(self):
        from library_package import build_package
        catalog = self.root / "catalog" / "index.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"assets":[]}', encoding="utf-8")
        with self.assertRaisesRegex(PackageError, "catalog pin not found"):
            build_package(self.root, ASSET, VERSION)


if __name__ == "__main__":
    unittest.main()
