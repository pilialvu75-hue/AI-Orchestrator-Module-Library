from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_resolver import (  # noqa: E402
    build_snapshot,
    export_snapshot,
    query,
    resolve,
)
from validate_snapshot import load as load_snapshot, validate as validate_snapshot  # noqa: E402


class LibraryResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write_json(
            self.root / "contracts" / "index.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-12T01:00:00Z",
                "contracts": [
                    {
                        "capability_id": "voice.stt",
                        "contract_id": "voice.stt.v1",
                        "contract_version": "1.0",
                        "status": "stable",
                        "description": "Stable STT contract",
                        "replacement": None,
                    },
                    {
                        "capability_id": "voice.stt.experimental",
                        "contract_id": "voice.stt.experimental.v1",
                        "contract_version": "1.0",
                        "status": "draft",
                        "description": "Draft STT contract",
                        "replacement": None,
                    },
                ],
            },
        )
        self.write_json(
            self.root / "catalog" / "needs.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-12T01:00:00Z",
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
            self.root / "catalog" / "lifecycle.json",
            {
                "schema_version": 1,
                "revision": 2,
                "updated_at": "2026-09-12T01:10:00Z",
                "events": [],
            },
        )

        assets = []
        assets.append(self.make_asset("voice.alpha", "1.0.0", score=0.90, effort="low", availability="active"))
        assets.append(self.make_asset("voice.beta", "2.0.0", score=0.95, effort="high", availability="active"))
        assets.append(self.make_asset("voice.legacy", "3.0.0", score=1.00, effort="trivial", availability="deprecated"))
        assets.append(self.make_asset("voice.revoked", "9.0.0", score=1.00, effort="trivial", availability="revoked"))
        assets.append(
            self.make_asset(
                "voice.draft",
                "1.0.0",
                score=0.99,
                effort="trivial",
                availability="active",
                capability="voice.stt.experimental",
                contract_id="voice.stt.experimental.v1",
            )
        )
        self.write_json(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "resolver-test-library",
                "catalog_version": "4.2.0",
                "updated_at": "2026-09-12T01:15:00Z",
                "assets": assets,
            },
        )

        self.write_json(
            self.root / "observations" / "voice.alpha" / "1.0.0.json",
            {
                "schema_version": 1,
                "asset_id": "voice.alpha",
                "version": "1.0.0",
                "revision": 5,
                "updated_at": "2026-09-12T01:20:00Z",
                "events": [
                    self.integration_event(f"alpha-{index}", success=index < 4)
                    for index in range(5)
                ],
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def integration_event(event_id: str, *, success: bool) -> dict:
        return {
            "event_id": event_id,
            "type": "integration",
            "occurred_at": "2026-09-12T01:20:00Z",
            "source": "cantiere",
            "outcome": "success" if success else "failure",
            "target": "android",
            "contract_id": "voice.stt.v1",
            "project_id": "fixture",
            "score": None,
            "notes": None,
            "metadata": {},
        }

    def make_asset(
        self,
        asset_id: str,
        version: str,
        *,
        score: float,
        effort: str,
        availability: str,
        capability: str = "voice.stt",
        status: str = "certified",
        contract_id: str = "voice.stt.v1",
    ) -> dict:
        path = self.root / "modules" / asset_id / version / "manifest.json"
        manifest = {
            "id": asset_id,
            "name": asset_id,
            "version": version,
            "kind": "integration_bundle",
            "status": status,
            "description": f"Fixture {asset_id}",
            "capabilities": [capability],
            "platforms": ["android"],
            "dependencies": [],
            "provenance": {
                "origin": "cantiere",
                "source_repository": None,
                "source_commit": None,
                "source_tag": None,
                "source_project_id": "fixture",
                "source_task_id": None,
                "license": "MIT",
                "license_file": None,
                "retrieved_at": None,
            },
            "validation": {
                "score": score,
                "tests_passed": True,
                "test_report": None,
                "validated_at": "2026-09-12T01:00:00Z",
                "validated_on": ["android"],
            },
            "security": {
                "reviewed": True,
                "reviewed_at": "2026-09-12T01:00:00Z",
                "known_vulnerabilities": 0,
                "sbom": None,
                "notes": None,
            },
            "integration": {
                "estimated_effort": effort,
                "adaptation_allowed": True,
                "known_constraints": [],
                "adapter_notes": None,
            },
            "connector": {
                "standard": "ai-orchestrator-lego",
                "standard_version": "1.0.0",
                "provides": [
                    {
                        "capability_id": capability,
                        "contract_id": contract_id,
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
                "upstream_repository": "https://github.com/example/fixture",
                "upstream_commit": "0123456789abcdef0123456789abcdef01234567",
            },
        }
        self.write_json(path, manifest)
        return {
            "id": asset_id,
            "version": version,
            "manifest": str(path.relative_to(self.root).as_posix()),
            "status": status,
            "availability": availability,
            "kind": "integration_bundle",
            "capabilities": [capability],
            "platforms": ["android"],
            "contracts": [contract_id],
        }

    def test_query_excludes_deprecated_and_revoked_by_default(self) -> None:
        candidates = query(
            self.root,
            capability="voice.stt",
            contract_id="voice.stt.v1",
            target="android",
        )
        self.assertEqual(["voice.alpha", "voice.beta"], [item["id"] for item in candidates])

    def test_balanced_policy_prefers_proven_low_effort_candidate(self) -> None:
        result = resolve(
            self.root,
            capability="voice.stt",
            contract_id="voice.stt.v1",
            target="android",
        )
        self.assertEqual("voice.alpha", result["selected"]["id"])
        self.assertEqual("balanced-v1", result["selected"]["ranking"]["policy"])
        self.assertGreater(
            result["selected"]["ranking"]["score"],
            result["candidates"][1]["ranking"]["score"],
        )

    def test_deprecated_is_explicit_and_never_outranks_active(self) -> None:
        candidates = query(
            self.root,
            capability="voice.stt",
            include_deprecated=True,
        )
        self.assertIn("voice.legacy", [item["id"] for item in candidates])
        self.assertEqual("active", candidates[0]["availability"])
        self.assertNotIn("voice.revoked", [item["id"] for item in candidates])

    def test_max_effort_filter_is_hard_constraint(self) -> None:
        candidates = query(
            self.root,
            capability="voice.stt",
            max_effort="low",
        )
        self.assertEqual(["voice.alpha"], [item["id"] for item in candidates])

    def test_require_stable_contract_excludes_draft_contract(self) -> None:
        permissive = query(self.root, capability="voice.stt.experimental")
        self.assertEqual(1, len(permissive))
        self.assertTrue(permissive[0]["warnings"])

        strict = query(
            self.root,
            capability="voice.stt.experimental",
            require_stable_contract=True,
        )
        self.assertEqual([], strict)

    def test_adaptable_tested_candidate_is_opt_in_and_never_implicit_certified(self) -> None:
        adaptable = self.make_asset(
            "voice.adaptable",
            "1.0.0",
            score=0.70,
            effort="medium",
            availability="active",
            status="tested",
        )
        catalog = json.loads((self.root / "catalog" / "index.json").read_text(encoding="utf-8"))
        catalog["assets"].append(adaptable)
        self.write_json(self.root / "catalog" / "index.json", catalog)

        strict = query(self.root, capability="voice.stt")
        self.assertNotIn("voice.adaptable", [item["id"] for item in strict])

        pragmatic = query(self.root, capability="voice.stt", include_adaptable=True)
        record = next(item for item in pragmatic if item["id"] == "voice.adaptable")
        self.assertEqual("tested", record["status"])
        self.assertTrue(record["integration"]["adaptation_allowed"])

    def test_snapshot_is_deterministic_and_includes_revoked_for_awareness(self) -> None:
        first = build_snapshot(self.root)
        second = build_snapshot(self.root)
        self.assertEqual(first, second)
        self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertIn("voice.revoked", [item["id"] for item in first["assets"]])

        output = self.root / "cache" / "library.json"
        result = export_snapshot(self.root, output)
        self.assertEqual("exported", result["result"])
        snapshot = load_snapshot(output)
        validate_snapshot(snapshot)
        self.assertEqual(first, snapshot)


if __name__ == "__main__":
    unittest.main()
