from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from library_curator import RESPONSE_SCHEMA

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
TRANSIENT_STATUSES = {429, 500, 502, 503, 504}

SYSTEM_PROMPT = """You are the AI Curator for the AI Orchestrator Module Library.
You are advisory only. The deterministic Library core is the sole authority for certification,
security, lifecycle, compatibility, deprecation/revocation and repository mutation.
Use only the supplied request context. Never invent asset refs or capabilities. Never claim that
an intake candidate is reusable production material. Return only JSON matching the supplied schema.
Keep summaries concise and decision-oriented; do not expose hidden chain-of-thought.
When ranking candidates, give short observable rationales, not private reasoning traces.
"""

GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "schema": {"type": "string", "enum": [RESPONSE_SCHEMA]},
        "request_id": {"type": "string"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "coverage_gap",
                            "candidate_ranking",
                            "reuse_recommendation",
                            "duplicate_hint",
                            "adapter_hint",
                            "health_warning",
                        ],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "summary": {"type": "string"},
                    "asset_refs": {"type": "array", "items": {"type": "string"}},
                    "capability_ids": {"type": "array", "items": {"type": "string"}},
                    "adapter_suggestions": {"type": "array", "items": {"type": "string"}},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "ranking_factors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "asset_ref": {"type": "string"},
                                "semantic_fit": {"type": "number", "minimum": 0, "maximum": 1},
                                "target_fit": {"type": "number", "minimum": 0, "maximum": 1},
                                "contract_fit": {"type": "number", "minimum": 0, "maximum": 1},
                                "evidence_strength": {"type": "number", "minimum": 0, "maximum": 1},
                                "integration_fit": {"type": "number", "minimum": 0, "maximum": 1},
                                "overall": {"type": "number", "minimum": 0, "maximum": 1},
                                "rationale": {"type": "string"},
                            },
                            "required": [
                                "asset_ref",
                                "semantic_fit",
                                "target_fit",
                                "contract_fit",
                                "evidence_strength",
                                "integration_fit",
                                "overall",
                                "rationale",
                            ],
                        },
                    },
                },
                "required": [
                    "type",
                    "confidence",
                    "summary",
                    "asset_refs",
                    "capability_ids",
                    "adapter_suggestions",
                    "warnings",
                    "ranking_factors",
                ],
            },
        },
    },
    "required": ["schema", "request_id", "recommendations"],
}

Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]
Sleeper = Callable[[float], None]


class GeminiProviderError(Exception):
    pass


def _task_instruction(request: dict[str, object]) -> str:
    task = request.get("task")
    if task == "rank_candidates":
        return (
            "Rank every supplied asset candidate for the requested capability. "
            "Return one candidate_ranking recommendation when candidates exist. "
            "asset_refs must be best-to-worst and ranking_factors must cover the same refs "
            "in the same order. Score semantic_fit, target_fit, contract_fit, "
            "evidence_strength, integration_fit and overall from 0 to 1. overall must be "
            "non-increasing in the returned order. Base scores only on supplied fields. "
            "A discovered/quarantined/normalized/tested intake asset may be ranked for evaluation "
            "but must never be returned as reuse_recommendation."
        )
    if task == "coverage":
        return (
            "Assess capability coverage against desired_candidates. Return coverage_gap when the "
            "known certified/active supply is insufficient. ranking_factors may be empty."
        )
    if task == "find_duplicates":
        return (
            "Identify only plausible duplicate or near-duplicate assets from the supplied context. "
            "Use duplicate_hint and cite exact asset_refs. ranking_factors may be empty."
        )
    if task == "suggest_adapters":
        return (
            "Suggest adapters only when the supplied contracts/platforms/integration constraints "
            "show a concrete mismatch. Use adapter_hint. ranking_factors may be empty."
        )
    if task == "health_review":
        return (
            "Surface only health or evidence concerns visible in the supplied context. "
            "Use health_warning. ranking_factors may be empty."
        )
    return "Follow the request task using only supplied context."


def _default_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise GeminiProviderError("Gemini response exceeded size limit")
            return int(response.status), payload
    except urllib.error.HTTPError as exc:
        payload = exc.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            payload = b""
        return int(exc.code), payload
    except urllib.error.URLError as exc:
        raise GeminiProviderError("Gemini network request failed") from exc


def _extract_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiProviderError("Gemini response contains no candidates")
    first = candidates[0]
    if not isinstance(first, dict):
        raise GeminiProviderError("Gemini candidate is invalid")
    content = first.get("content")
    if not isinstance(content, dict):
        raise GeminiProviderError("Gemini candidate contains no content")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise GeminiProviderError("Gemini candidate contains no parts")

    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            texts.append(text)
    if not texts:
        raise GeminiProviderError("Gemini candidate contains no text")
    return "".join(texts)


class GeminiCuratorProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: Transport = _default_transport,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key or not resolved_key.strip():
            raise GeminiProviderError("GEMINI_API_KEY is not configured")
        if timeout_seconds <= 0:
            raise GeminiProviderError("timeout_seconds must be > 0")
        if max_retries < 0 or max_retries > 5:
            raise GeminiProviderError("max_retries must be between 0 and 5")

        self._api_key = resolved_key.strip()
        self._model = (
            model
            or os.environ.get("AI_ORCHESTRATOR_CURATOR_GEMINI_MODEL")
            or DEFAULT_MODEL
        ).strip()
        if not self._model:
            raise GeminiProviderError("Gemini model is empty")
        self._timeout_seconds = float(timeout_seconds)
        self._max_retries = max_retries
        self._transport = transport
        self._sleeper = sleeper

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    @property
    def model(self) -> str:
        return self._model

    def _endpoint(self) -> str:
        model = urllib.parse.quote(self._model, safe="-._")
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )

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
                "responseFormat": {
                    "text": {
                        "mimeType": "application/json",
                        "schema": GEMINI_RESPONSE_SCHEMA,
                    }
                },
            },
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise GeminiProviderError("Gemini request exceeded size limit")
        return encoded

    def advise(self, request: dict[str, object]) -> dict[str, object]:
        body = self._body(request)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
            "User-Agent": "AI-Orchestrator-Module-Library-Curator/1.5",
        }
        endpoint = self._endpoint()

        attempts = self._max_retries + 1
        last_status: int | None = None
        for attempt in range(attempts):
            try:
                status, raw = self._transport(
                    endpoint,
                    headers,
                    body,
                    self._timeout_seconds,
                )
            except GeminiProviderError:
                if attempt >= self._max_retries:
                    raise
                self._sleeper(min(2.0 ** attempt, 4.0))
                continue

            last_status = status
            if 200 <= status < 300:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    raise GeminiProviderError("Gemini returned invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise GeminiProviderError("Gemini returned an invalid response object")
                text = _extract_text(payload)
                try:
                    advice = json.loads(text)
                except Exception as exc:
                    raise GeminiProviderError("Gemini structured output is invalid JSON") from exc
                if not isinstance(advice, dict):
                    raise GeminiProviderError("Gemini structured output must be an object")
                return advice

            if status in TRANSIENT_STATUSES and attempt < self._max_retries:
                self._sleeper(min(2.0 ** attempt, 4.0))
                continue
            raise GeminiProviderError(f"Gemini API request failed with HTTP {status}")

        raise GeminiProviderError(
            "Gemini API request failed"
            + (f" with HTTP {last_status}" if last_status is not None else "")
        )
