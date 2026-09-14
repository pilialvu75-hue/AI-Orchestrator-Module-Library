from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_curator_gemini as runner  # noqa: E402
from library_curator import CuratorError  # noqa: E402
from library_curator_gemini import GeminiProviderError  # noqa: E402


class FakeProvider:
    name = "test:provider"


class CuratorOperationalDispatchTest(unittest.TestCase):
    def test_specialized_tasks_never_use_generic_runner(self) -> None:
        cases = [
            ("rank_candidates", "run_semantic_ranking"),
            ("find_duplicates", "run_duplicate_analysis"),
            ("suggest_adapters", "run_adapter_analysis"),
            ("health_review", "run_health_review"),
        ]

        for task, function_name in cases:
            with self.subTest(task=task):
                expected = {"route": task}
                with (
                    patch.object(runner, function_name, return_value=expected) as specialized,
                    patch.object(runner, "run_curator") as generic,
                ):
                    result = runner.dispatch_curator(
                        Path("/tmp/library"),
                        FakeProvider(),
                        task=task,
                        capability_id="storage.local_db",
                    )
                self.assertEqual(expected, result)
                specialized.assert_called_once()
                generic.assert_not_called()

    def test_coverage_uses_provider_neutral_core_runner(self) -> None:
        expected = {"route": "coverage"}
        with patch.object(runner, "run_curator", return_value=expected) as generic:
            result = runner.dispatch_curator(
                Path("/tmp/library"),
                FakeProvider(),
                task="coverage",
                capability_id=None,
            )
        self.assertEqual(expected, result)
        generic.assert_called_once()

    def test_candidate_specific_tasks_require_capability(self) -> None:
        for task in ("rank_candidates", "find_duplicates", "suggest_adapters"):
            with self.subTest(task=task):
                with self.assertRaisesRegex(CuratorError, "requires --capability"):
                    runner.dispatch_curator(
                        Path("/tmp/library"),
                        FakeProvider(),
                        task=task,
                        capability_id=None,
                    )

    def test_health_review_may_cover_all_modules(self) -> None:
        expected = {"route": "health_review"}
        with patch.object(runner, "run_health_review", return_value=expected) as health:
            result = runner.dispatch_curator(
                Path("/tmp/library"),
                FakeProvider(),
                task="health_review",
                capability_id=None,
            )
        self.assertEqual(expected, result)
        health.assert_called_once()

    def test_lazy_provider_does_not_require_secret_until_advise(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            provider = runner.LazyGeminiCuratorProvider(
                model="gemini-test",
                timeout_seconds=1.0,
            )
            self.assertEqual("gemini:gemini-test", provider.name)
            with self.assertRaisesRegex(GeminiProviderError, "GEMINI_API_KEY"):
                provider.advise({})

    def test_deterministic_specialized_route_can_skip_secret(self) -> None:
        expected = {
            "provider": "deterministic-core:no-candidates",
            "core_verification": {"ai_called": False},
        }
        with patch.dict(os.environ, {}, clear=True):
            provider = runner.LazyGeminiCuratorProvider(model="gemini-test")
            with patch.object(
                runner,
                "run_semantic_ranking",
                return_value=expected,
            ) as semantic:
                result = runner.dispatch_curator(
                    Path("/tmp/library"),
                    provider,
                    task="rank_candidates",
                    capability_id="storage.local_db",
                )
        self.assertEqual(expected, result)
        semantic.assert_called_once()

    def test_workflow_does_not_precheck_gemini_secret(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "run-curator-gemini.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Verify Gemini credential is configured", workflow)
        self.assertIn("GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}", workflow)


if __name__ == "__main__":
    unittest.main()
