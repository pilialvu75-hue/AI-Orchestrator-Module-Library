from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from library_curator import ALLOWED_TASKS, CuratorError, run_curator
from library_curator_gemini import GeminiCuratorProvider, GeminiProviderError
from library_curator_health import run_health_review
from library_curator_relations import run_adapter_analysis, run_duplicate_analysis
from library_curator_semantic import run_semantic_ranking


def dispatch_curator(
    root: Path,
    provider: GeminiCuratorProvider,
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
        description="Run the AI Curator through the Gemini API"
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
        provider = GeminiCuratorProvider(
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
