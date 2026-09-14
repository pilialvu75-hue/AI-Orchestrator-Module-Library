from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_curator_gemini as runner  # noqa: E402
from library_curator import CuratorError  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
