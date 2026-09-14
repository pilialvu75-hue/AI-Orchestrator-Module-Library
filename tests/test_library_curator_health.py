from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_curator import RESPONSE_SCHEMA, CuratorError  # noqa: E402
from library_curator_health import run_health_review  # noqa: E402


class RecordingProvider:
    name = "test:health-provider"

    def __init__(self, responder=None) -> None:
        self.calls = 0
        self.last_request = None
        self._responder = responder

    def advise(self, request: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        self.last_request = request
        if self._responder is None:
            raise AssertionError("provider must not be called")
        return self._responder(request)


class LibraryCuratorHealthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write(
            self.root / "catalog" / "needs.json",
            {
                "schema_version": 1,
                "updated_at": "2026-09-14T00:00:00Z",
                "items": [
                    {
                        "capability_id": "storage.local_db",
                        "title": "Local database",
                        "priority": "high",
                        "desired_candidates": 2,
                        "status": "needed",
                        "targets": ["android"],
                    }
                ],
            },
        )
        self._write(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "test-library",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-14T00:00:00Z",
                "assets": [],
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def _add_module(self, asset_id: str = "storage.test_db") -> str:
        version = "1.0.0"
        ref = f"{asset_id}@{version}"
        manifest = {
            "id": asset_id,
            "name": "Test local database",
            "version": version,
            "kind": "module",
            "status": "certified",
            "description": "Test database module",
            "capabilities": ["storage.local_db"],
            "platforms": ["android"],
            "provenance": {
                "origin": "researcher",
                "source_repository": "https://github.com/example/db",
                "source_commit": "0123456789abcdef0123456789abcdef01234567",
                "license": "MIT",
            },
            "validation": {
                "score": 0.95,
                "tests_passed": True,
                "validated_on": ["android"],
            },
            "security": {
                "reviewed": True,
                "known_vulnerabilities": 0,
            },
            "integration": {
                "estimated_effort": "low",
                "adaptation_allowed": True,
                "known_constraints": [],
            },
            "connector": {
                "standard": "ai-orchestrator-lego",
                "standard_version": "1.0.0",
                "provides": [
                    {
                        "capability_id": "storage.local_db",
                        "contract_id": "storage.local_db.v1",
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
                "upstream_repository": "https://github.com/example/db",
                "upstream_commit": "0123456789abcdef0123456789abcdef01234567",
            },
        }
        self._write(
            self.root / "modules" / asset_id / version / "manifest.json",
            manifest,
        )
        catalog = json.loads(
            (self.root / "catalog" / "index.json").read_text(encoding="utf-8")
        )
        catalog["assets"].append(
            {
                "id": asset_id,
                "version": version,
                "manifest": f"modules/{asset_id}/{version}/manifest.json",
                "status": "certified",
                "availability": "active",
                "kind": "module",
                "capabilities": ["storage.local_db"],
                "platforms": ["android"],
                "contracts": ["storage.local_db.v1"],
            }
        )
        self._write(self.root / "catalog" / "index.json", catalog)
        return ref

    def _history(self, asset_id: str, events: list[dict]) -> None:
        self._write(
            self.root / "observations" / asset_id / "1.0.0.json",
            {
                "schema_version": 1,
                "asset_id": asset_id,
                "version": "1.0.0",
                "revision": len(events),
                "updated_at": events[-1]["occurred_at"] if events else None,
                "events": events,
            },
        )

    @staticmethod
    def _event(
        event_id: str,
        outcome: str,
        hour: int,
        *,
        notes: str = "private diagnostic note",
    ) -> dict:
        return {
            "event_id": event_id,
            "type": "integration",
            "occurred_at": f"2026-09-14T0{hour}:00:00Z",
            "source": "cantiere",
            "outcome": outcome,
            "target": "android",
            "contract_id": "storage.local_db.v1",
            "project_id": "secret-project-id",
            "score": None,
            "notes": notes,
            "metadata": {"internal_path": "/private/workspace"},
        }

    def test_healthy_history_skips_ai_call(self) -> None:
        ref = self._add_module()
        asset_id = ref.split("@", 1)[0]
        self._history(
            asset_id,
            [
                self._event("ok-1", "success", 1),
                self._event("ok-2", "success", 2),
                self._event("ok-3", "success", 3),
            ],
        )
        before = (self.root / "catalog" / "index.json").read_bytes()
        provider = RecordingProvider()

        result = run_health_review(
            self.root,
            provider,
            capability_id="storage.local_db",
        )

        self.assertEqual(0, provider.calls)
        self.assertFalse(result["core_verification"]["ai_called"])
        self.assertEqual([], result["advice"]["recommendations"])
        self.assertEqual([], result["core_verification"]["health_signals"][ref])
        self.assertEqual(before, (self.root / "catalog" / "index.json").read_bytes())

    def test_degrading_history_is_explained_but_not_mutated(self) -> None:
        ref = self._add_module()
        asset_id = ref.split("@", 1)[0]
        self._history(
            asset_id,
            [
                self._event("run-1", "success", 1),
                self._event("run-2", "failure", 2),
                self._event("run-3", "failure", 3),
            ],
        )
        observation_path = self.root / "observations" / asset_id / "1.0.0.json"
        before = observation_path.read_bytes()

        def responder(request: dict[str, object]) -> dict[str, object]:
            return {
                "schema": RESPONSE_SCHEMA,
                "request_id": request["request_id"],
                "recommendations": [
                    {
                        "type": "health_warning",
                        "confidence": 0.94,
                        "summary": "Recent integration outcomes show a degrading pattern.",
                        "asset_refs": [ref],
                        "capability_ids": ["storage.local_db"],
                        "adapter_suggestions": [],
                        "warnings": ["Two most recent integrations failed."],
                        "ranking_factors": [],
                    }
                ],
            }

        provider = RecordingProvider(responder)
        result = run_health_review(
            self.root,
            provider,
            capability_id="storage.local_db",
        )

        self.assertEqual(1, provider.calls)
        signals = result["core_verification"]["health_signals"][ref]
        self.assertIn("integration_failures_observed", signals)
        self.assertIn("low_integration_success_rate", signals)
        self.assertIn("recent_integration_failure_streak", signals)
        self.assertTrue(result["core_verification"]["ai_called"])
        self.assertEqual("health_warning", result["advice"]["recommendations"][0]["type"])
        self.assertEqual(before, observation_path.read_bytes())

    def test_provider_never_receives_sensitive_observation_fields(self) -> None:
        ref = self._add_module()
        asset_id = ref.split("@", 1)[0]
        self._history(
            asset_id,
            [
                self._event("run-1", "success", 1),
                self._event("run-2", "failure", 2),
                self._event("run-3", "failure", 3),
            ],
        )

        def responder(request: dict[str, object]) -> dict[str, object]:
            rendered = json.dumps(request, sort_keys=True)
            self.assertNotIn("private diagnostic note", rendered)
            self.assertNotIn("secret-project-id", rendered)
            self.assertNotIn("/private/workspace", rendered)
            self.assertNotIn('"metadata"', rendered)
            self.assertNotIn('"notes"', rendered)
            return {
                "schema": RESPONSE_SCHEMA,
                "request_id": request["request_id"],
                "recommendations": [
                    {
                        "type": "health_warning",
                        "confidence": 0.9,
                        "summary": "Observed integration failures require attention.",
                        "asset_refs": [ref],
                        "capability_ids": ["storage.local_db"],
                        "adapter_suggestions": [],
                        "warnings": ["Failure trend observed."],
                        "ranking_factors": [],
                    }
                ],
            }

        provider = RecordingProvider(responder)
        run_health_review(
            self.root,
            provider,
            capability_id="storage.local_db",
        )
        self.assertEqual(1, provider.calls)

    def test_health_warning_cannot_cite_module_without_signal(self) -> None:
        degraded_ref = self._add_module("storage.degraded_db")
        healthy_ref = self._add_module("storage.healthy_db")
        self._history(
            "storage.degraded_db",
            [
                self._event("bad-1", "success", 1),
                self._event("bad-2", "failure", 2),
                self._event("bad-3", "failure", 3),
            ],
        )
        self._history(
            "storage.healthy_db",
            [
                self._event("good-1", "success", 1),
                self._event("good-2", "success", 2),
                self._event("good-3", "success", 3),
            ],
        )

        def responder(request: dict[str, object]) -> dict[str, object]:
            return {
                "schema": RESPONSE_SCHEMA,
                "request_id": request["request_id"],
                "recommendations": [
                    {
                        "type": "health_warning",
                        "confidence": 0.8,
                        "summary": "Unsupported warning.",
                        "asset_refs": [healthy_ref],
                        "capability_ids": ["storage.local_db"],
                        "adapter_suggestions": [],
                        "warnings": ["Invented concern."],
                        "ranking_factors": [],
                    }
                ],
            }

        provider = RecordingProvider(responder)
        with self.assertRaisesRegex(CuratorError, "without deterministic health signals"):
            run_health_review(
                self.root,
                provider,
                capability_id="storage.local_db",
            )
        self.assertEqual(1, provider.calls)
        self.assertNotEqual(degraded_ref, healthy_ref)


if __name__ == "__main__":
    unittest.main()
