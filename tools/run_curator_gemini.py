from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from library_curator import (
    ALLOWED_TASKS,
    CuratorError,
    LibraryCuratorProvider,
    run_curator,
)
from library_curator_gemini import (
    DEFAULT_MODEL,
    GeminiCuratorProvider,
    GeminiProviderError,
)
from library_curator_health import run_health_review
from library_curator_relations import run_adapter_analysis, run_duplicate_analysis
from library_curator_semantic import run_semantic_ranking


class LazyGeminiCuratorProvider:
    """Instantiate the network provider only when a task truly needs AI."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise GeminiProviderError("timeout_seconds must be > 0")
        resolved_model = (
            model
            or os.environ.get("AI_ORCHESTRATOR_CURATOR_GEMINI_MODEL")
            or DEFAULT_MODEL
        ).strip()
        if not resolved_model:
            raise GeminiProviderError("Gemini model is empty")

        self._model = resolved_model
        self._timeout_seconds = float(timeout_seconds)
        self._delegate: GeminiCuratorProvider | None = None

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    def advise(self, request: dict[str, object]) -> dict[str, object]:
        delegate = self._delegate
        if delegate is None:
            delegate = GeminiCuratorProvider(
                model=self._model,
                timeout_seconds=self._timeout_seconds,
            )
            self._delegate = delegate
        return delegate.advise(request)


def dispatch_curator(
    root: Path,
    provider: LibraryCuratorProvider,
    *,
    task: str,
    capability_id: str | None,
) -> dict[str, object]:
    """Route workflow execution through the strongest task-specific verifier."""

    if task == "rank_candidates":
        if not capability_id:
            raise CuratorError("rank_candidates requires --capability")
        return run_semantic_ranking(
            root,
            provider,
            capability_id=capability_id,
        )
    if task == "find_duplicates":
        if not capability_id:
            raise CuratorError("find_duplicates requires --capability")
        return run_duplicate_analysis(
            root,
            provider,
            capability_id=capability_id,
        )
    if task == "suggest_adapters":
        if not capability_id:
            raise CuratorError("suggest_adapters requires --capability")
        return run_adapter_analysis(
            root,
            provider,
            capability_id=capability_id,
        )
    if task == "health_review":
        return run_health_review(
            root,
            provider,
            capability_id=capability_id,
        )
    return run_curator(
        root,
        provider,
        task=task,
        capability_id=capability_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the AI Curator through the Gemini API when AI is required"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--task", choices=sorted(ALLOWED_TASKS), required=True)
    parser.add_argument("--capability")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    try:
        provider = LazyGeminiCuratorProvider(
            model=args.model,
            timeout_seconds=args.timeout,
        )
        result = dispatch_curator(
            args.root.resolve(),
            provider,
            task=args.task,
            capability_id=args.capability,
        )
    except (CuratorError, GeminiProviderError) as exc:
        print(f"LIBRARY CURATOR GEMINI FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
