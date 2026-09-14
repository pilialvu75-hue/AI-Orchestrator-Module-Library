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
    GEMINI_RESPONSE_SCHEMA,
    MAX_REQUEST_BYTES,
    SYSTEM_PROMPT,
    GeminiCuratorProvider,
    GeminiProviderError,
    _task_instruction,
)
from library_curator_health import run_health_review
from library_curator_relations import run_adapter_analysis, run_duplicate_analysis
from library_curator_semantic import run_semantic_ranking


CURRENT_GEMINI_MODEL = "gemini-3.8-flash"
LEGACY_MODEL_ALIASES = {
    "gemini-3.6-flash": CURRENT_GEMINI_MODEL,
}


def normalize_model(model: str | None) -> str:
    requested = (
        model
        or os.environ.get("AI_ORCHESTRATOR_CURATOR_GEMINI_MODEL")
        or CURRENT_GEMINI_MODEL
    ).strip()
    if not requested:
        raise GeminiProviderError("Gemini model is empty")
    return LEGACY_MODEL_ALIASES.get(requested, requested)


class GenerateContentGeminiCuratorProvider(GeminiCuratorProvider):
    """Gemini provider using the legacy generateContent structured-output contract.

    The generateContent endpoint expects responseMimeType + responseJsonSchema
    inside generationConfig. responseFormat belongs to the newer Interactions API.
    """

    def _body(self, request: dict[str, object]) -> bytes:
        request_json = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        prompt = (
            "TASK INSTRUCTIONS:\n"
            + _task_instruction(request)
            + "\n\nREQUEST JSON:\n"
            + request_json
        )
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseJsonSchema": GEMINI_RESPONSE_SCHEMA,
            },
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise GeminiProviderError("Gemini request exceeded size limit")
        return encoded


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

        self._model = normalize_model(model)
        self._timeout_seconds = float(timeout_seconds)
        self._delegate: GenerateContentGeminiCuratorProvider | None = None

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    def advise(self, request: dict[str, object]) -> dict[str, object]:
        delegate = self._delegate
        if delegate is None:
            delegate = GenerateContentGeminiCuratorProvider(
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
