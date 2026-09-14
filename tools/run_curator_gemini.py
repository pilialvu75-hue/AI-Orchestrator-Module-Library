from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from library_curator import ALLOWED_TASKS, CuratorError, run_curator
from library_curator_gemini import GeminiCuratorProvider, GeminiProviderError


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
        result = run_curator(
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
