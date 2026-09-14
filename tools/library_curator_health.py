from __future__ import annotations

import hashlib
import json
from pathlib import Path

from library_curator import (
    RESULT_SCHEMA,
    RESPONSE_SCHEMA,
    CuratorError,
    LibraryCuratorProvider,
    build_request,
    verify_response,
)
from library_history import AssetRef, load_history, summarize_history

MAX_RECENT_EVENTS = 20


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_recent_events(history: dict[str, object]) -> list[dict[str, object]]:
    events = history.get("events")
    if not isinstance(events, list):
        return []

    result: list[dict[str, object]] = []
    for event in events[-MAX_RECENT_EVENTS:]:
        if not isinstance(event, dict):
            continue
        result.append(
            {
                "type": event.get("type"),
                "occurred_at": event.get("occurred_at"),
                "source": event.get("source"),
                "outcome": event.get("outcome"),
                "target": event.get("target"),
                "contract_id": event.get("contract_id"),
                "score": event.get("score"),
            }
        )
    return result


def _signals(summary: dict[str, object], history: dict[str, object]) -> list[str]:
    signals: list[str] = []
    revision = int(summary.get("revision") or 0)
    attempts = int(summary.get("reuse_count") or 0)
    failures = int(summary.get("failed_integrations") or 0)
    incident_count = int(summary.get("incident_count") or 0)
    success_rate = summary.get("success_rate")

    if revision == 0:
        signals.append("no_operational_history")
    if failures > 0:
        signals.append("integration_failures_observed")
    if (
        attempts >= 3
        and isinstance(success_rate, (int, float))
        and not isinstance(success_rate, bool)
        and float(success_rate) < 0.80
    ):
        signals.append("low_integration_success_rate")
    if incident_count > 0:
        signals.append("incidents_observed")

    compatibility = summary.get("compatibility")
    if isinstance(compatibility, dict) and any(
        isinstance(value, dict) and value.get("outcome") == "incompatible"
        for value in compatibility.values()
    ):
        signals.append("incompatible_observation")

    latest_validation = summary.get("latest_validation")
    if isinstance(latest_validation, dict):
        outcome = latest_validation.get("outcome")
        score = latest_validation.get("score")
        if outcome in {"fail", "warning"} or (
            isinstance(score, (int, float))
            and not isinstance(score, bool)
            and float(score) < 0.80
        ):
            signals.append("latest_validation_concern")

    events = history.get("events")
    if isinstance(events, list):
        integrations = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "integration"
        ]
        recent = integrations[-2:]
        if len(recent) == 2 and all(event.get("outcome") == "failure" for event in recent):
            signals.append("recent_integration_failure_streak")

    return sorted(set(signals))


def _safe_observation_view(
    root: Path,
    asset: dict[str, object],
) -> dict[str, object]:
    asset_id = str(asset.get("id") or "")
    version = str(asset.get("version") or "")
    ref = AssetRef(asset_id, version)
    history = load_history(root, ref)
    summary = summarize_history(history)

    compatibility = summary.get("compatibility")
    safe_compatibility: list[dict[str, object]] = []
    if isinstance(compatibility, dict):
        for value in compatibility.values():
            if not isinstance(value, dict):
                continue
            safe_compatibility.append(
                {
                    "outcome": value.get("outcome"),
                    "occurred_at": value.get("occurred_at"),
                    "target": value.get("target"),
                    "contract_id": value.get("contract_id"),
                }
            )

    latest_validation = summary.get("latest_validation")
    safe_validation = None
    if isinstance(latest_validation, dict):
        safe_validation = {
            "outcome": latest_validation.get("outcome"),
            "score": latest_validation.get("score"),
            "occurred_at": latest_validation.get("occurred_at"),
            "target": latest_validation.get("target"),
        }

    return {
        "asset_ref": str(asset.get("ref") or f"{asset_id}@{version}"),
        "availability": asset.get("availability"),
        "revision": int(summary.get("revision") or 0),
        "reuse_count": int(summary.get("reuse_count") or 0),
        "successful_integrations": int(summary.get("successful_integrations") or 0),
        "failed_integrations": int(summary.get("failed_integrations") or 0),
        "success_rate": summary.get("success_rate"),
        "incident_count": int(summary.get("incident_count") or 0),
        "benchmark_count": int(summary.get("benchmark_count") or 0),
        "last_observed_at": summary.get("last_observed_at"),
        "latest_validation": safe_validation,
        "compatibility": sorted(
            safe_compatibility,
            key=lambda item: (
                str(item.get("target") or ""),
                str(item.get("contract_id") or ""),
            ),
        ),
        "recent_events": _safe_recent_events(history),
        "signals": _signals(summary, history),
    }


def _health_request(
    root: Path,
    *,
    capability_id: str | None,
) -> tuple[dict[str, object], dict[str, list[str]]]:
    request = build_request(
        root,
        task="health_review",
        capability_id=capability_id,
    )
    context = request.get("context")
    if not isinstance(context, dict):
        raise CuratorError("health review request context is invalid")
    assets = context.get("assets")
    if not isinstance(assets, list):
        raise CuratorError("health review request assets are invalid")

    module_assets = [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("source_area") == "modules"
    ]
    observations = [
        _safe_observation_view(root, asset)
        for asset in module_assets
    ]
    context["assets"] = module_assets
    context["observations"] = observations

    request["context"] = context
    request["context_sha256"] = _sha256(context)
    request_seed = {
        "task": request.get("task"),
        "capability_id": request.get("capability_id"),
        "context": context,
    }
    request["request_id"] = _sha256(request_seed)[:24]

    signal_by_ref = {
        str(item["asset_ref"]): [str(signal) for signal in item["signals"]]
        for item in observations
        if isinstance(item.get("asset_ref"), str)
        and isinstance(item.get("signals"), list)
    }
    return request, signal_by_ref


def _result(
    *,
    provider_name: str,
    request: dict[str, object],
    advice: dict[str, object],
    ai_called: bool,
    signal_by_ref: dict[str, list[str]],
) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "provider": provider_name,
        "request": request,
        "advice": advice,
        "core_verification": {
            "passed": True,
            "advisory_only": True,
            "library_mutated": False,
            "authority": "deterministic-library-core",
            "ai_called": ai_called,
            "health_signals": signal_by_ref,
        },
    }


def run_health_review(
    root: Path,
    provider: LibraryCuratorProvider,
    *,
    capability_id: str | None = None,
) -> dict[str, object]:
    """Review operational health without granting AI lifecycle authority.

    The deterministic core first derives factual signals from append-only observations.
    Gemini may explain those signals, but accepted health warnings must cite exact known
    module refs that have at least one deterministic signal. No notes, metadata or project
    identifiers are sent to the provider.
    """

    request, signal_by_ref = _health_request(
        root,
        capability_id=capability_id,
    )

    actionable = {
        ref: signals
        for ref, signals in signal_by_ref.items()
        if any(signal != "no_operational_history" for signal in signals)
    }
    if not actionable:
        deterministic = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [],
        }
        advice = verify_response(request, deterministic)
        return _result(
            provider_name="deterministic-core:no-health-degradation",
            request=request,
            advice=advice,
            ai_called=False,
            signal_by_ref=signal_by_ref,
        )

    raw = provider.advise(request)
    advice = verify_response(request, raw)
    recommendations = advice.get("recommendations")
    if not isinstance(recommendations, list):
        raise CuratorError("health review advice is invalid")

    for index, item in enumerate(recommendations):
        if not isinstance(item, dict) or item.get("type") != "health_warning":
            raise CuratorError(
                "health review accepts only health_warning recommendations"
            )
        refs = item.get("asset_refs")
        if not isinstance(refs, list) or not refs:
            raise CuratorError(
                f"health_warning[{index}] must cite at least one known module"
            )
        unsupported = [
            str(ref)
            for ref in refs
            if str(ref) not in signal_by_ref or not signal_by_ref[str(ref)]
        ]
        if unsupported:
            raise CuratorError(
                f"health_warning[{index}] cites modules without deterministic health signals: "
                + ", ".join(sorted(unsupported))
            )
        if item.get("adapter_suggestions"):
            raise CuratorError(
                f"health_warning[{index}] cannot contain adapter_suggestions"
            )
        if item.get("ranking_factors"):
            raise CuratorError(
                f"health_warning[{index}] cannot contain ranking_factors"
            )

    return _result(
        provider_name=provider.name,
        request=request,
        advice=advice,
        ai_called=True,
        signal_by_ref=signal_by_ref,
    )
