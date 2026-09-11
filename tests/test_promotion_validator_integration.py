from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import validate_library  # noqa: E402
from library_pipeline import AssetRef, promote  # noqa: E402


class PromotionValidatorIntegrationTest(unittest.TestCase):
    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_promoted_asset_passes_repository_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ref = AssetRef("voice.integration_stt", "1.0.0")

            self.write_json(
                root / "contracts" / "index.json",
                {
                    "schema_version": 1,
                    "updated_at": "2026-09-11T00:00:00Z",
                    "contracts": [
                        {
                            "capability_id": "voice.stt",
                            "contract_id": "voice.stt.v1",
                            "contract_version": "1.0",
                            "status": "stable",
                            "description": "Test STT contract",
                            "replacement": None,
                        }
                    ],
                },
            )
            self.write_json(
                root / "catalog" / "needs.json",
                {
                    "schema_version": 1,
                    "updated_at": "2026-09-11T00:00:00Z",
                    "items": [
                        {
                            "capability_id": "voice.stt",
                            "title": "Speech to text",
                            "priority": "high",
                            "desired_candidates": 2,
                            "status": "needed",
                            "targets": ["android"],
                        }
                    ],
                },
            )
            self.write_json(
                root / "catalog" / "index.json",
                {
                    "schema_version": 1,
                    "library_id": "integration-test-library",
                    "catalog_version": "1.0.0",
                    "updated_at": "2026-09-11T00:00:00Z",
                    "assets": [],
                },
            )

            base = root / "intake" / ref.asset_id / ref.version
            (base / "provenance").mkdir(parents=True)
            (base / "provenance" / "LICENSE").write_text("MIT\n", encoding="utf-8")
            self.write_json(
                base / "manifest.json",
                {
                    "id": ref.asset_id,
                    "name": "Integration STT",
                    "version": ref.version,
                    "kind": "integration_bundle",
                    "status": "tested",
                    "description": "Integration fixture",
                    "capabilities": ["voice.stt"],
                    "platforms": ["android"],
                    "languages": ["dart"],
                    "frameworks": ["flutter"],
                    "entry_paths": [],
                    "dependencies": [],
                    "provenance": {
                        "origin": "researcher",
                        "source_repository": "https://github.com/example/project",
                        "source_commit": "0123456789abcdef0123456789abcdef01234567",
                        "source_tag": None,
                        "source_project_id": None,
                        "source_task_id": None,
                        "license": "MIT",
                        "license_file": "provenance/LICENSE",
                        "retrieved_at": "2026-09-11T00:00:00Z",
                    },
                    "validation": {
                        "score": 0.95,
                        "tests_passed": True,
                        "test_report": None,
                        "validated_at": "2026-09-11T01:00:00Z",
                        "validated_on": ["android"],
                    },
                    "security": {
                        "reviewed": True,
                        "reviewed_at": "2026-09-11T01:30:00Z",
                        "known_vulnerabilities": 0,
                        "sbom": None,
                        "notes": None,
                    },
                    "integration": {
                        "estimated_effort": "low",
                        "adaptation_allowed": True,
                        "known_constraints": [],
                        "adapter_notes": None,
                    },
                    "connector": {
                        "standard": "ai-orchestrator-lego",
                        "standard_version": "1.0.0",
                        "provides": [
                            {
                                "capability_id": "voice.stt",
                                "contract_id": "voice.stt.v1",
                                "contract_version": "1.0",
                            }
                        ],
                        "requires": [],
                        "integration_mode": "adapter",
                        "adapters": [],
                        "configuration_schema": None,
                        "healthcheck": None,
                    },
                    "payload": {
                        "type": "upstream_reference",
                        "path": None,
                        "sha256": None,
                        "upstream_repository": "https://github.com/example/project",
                        "upstream_commit": "0123456789abcdef0123456789abcdef01234567",
                    },
                    "quality": {
                        "reuse_count": 0,
                        "successful_integrations": 0,
                        "failed_integrations": 0,
                        "last_used_at": None,
                    },
                    "deprecation": {"reason": None, "replacement": None},
                },
            )

            result = promote(root, ref)
            self.assertEqual("promoted", result["result"])

            previous_root = validate_library.ROOT
            validate_library.ROOT = root
            try:
                registry = validate_library.validate_contracts()
                validate_library.validate_needs(registry)
                module_manifests = {}
                for path in validate_library.manifest_files("modules"):
                    asset_id, version, status, capabilities = validate_library.validate_manifest(
                        path,
                        under_modules=True,
                        contract_registry=registry,
                    )
                    module_manifests[(asset_id, version)] = (path, status, capabilities)
                validate_library.validate_catalog(module_manifests)
            finally:
                validate_library.ROOT = previous_root


if __name__ == "__main__":
    unittest.main()
