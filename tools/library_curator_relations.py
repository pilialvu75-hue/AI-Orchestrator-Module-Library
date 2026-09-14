from __future__ import annotations

from pathlib import Path

from library_curator import (
    RESULT_SCHEMA,
    RESPONSE_SCHEMA,
    CuratorError,
    LibraryCuratorProvider,
    build_request,
    verify_response,
)


def _asset_refs(request: dict[str, object]) -> list[str]:
    context = request.get("context")
    if not isinstance(context, dict):
        raise CuratorError("curator relation request context is invalid")
    assets = context.get("assets")
    if not isinstance(assets, list):
        raise CuratorError("curator relation request assets are invalid")
    return [
        str(asset.get("ref"))
        for asset in assets
        if isinstance(asset, dict) and asset.get("ref")
    ]


def _result(
    *,
    provider_name: str,
    request: dict[str, object],
    advice: dict[str, object],
    ai_called: bool,
    alternative_candidate_refs: list[str],
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
            "alternative_candidate_refs": alternative_candidate_refs,
        },
    }


def run_duplicate_analysis(
    root: Path,
    provider: LibraryCuratorProvider,
    *,
    capability_id: str,
) -> dict[str, object]:
    """Find possible duplicate/near-equivalent candidates for one capability.

    Every asset providing the capability is deterministically an *alternative candidate*.
    AI is used only to flag subsets that appear duplicate or near-duplicate from supplied
    metadata. A duplicate hint never changes lifecycle or reuse eligibility.
    """

    request = build_request(
        root,
        task="find_duplicates",
        capability_id=capability_id,
    )
    refs = _asset_refs(request)

    if len(refs) < 2:
        deterministic = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [],
        }
        advice = verify_response(request, deterministic)
        return _result(
            provider_name="deterministic-core:insufficient-candidates",
            request=request,
            advice=advice,
            ai_called=False,
            alternative_candidate_refs=refs,
        )

    raw = provider.advise(request)
    advice = verify_response(request, raw)
    recommendations = advice.get("recommendations")
    if not isinstance(recommendations, list):
        raise CuratorError("duplicate analysis advice is invalid")

    for index, item in enumerate(recommendations):
        if not isinstance(item, dict) or item.get("type") != "duplicate_hint":
            raise CuratorError(
                "duplicate analysis accepts only duplicate_hint recommendations"
            )
        cited = item.get("asset_refs")
        if not isinstance(cited, list) or len(cited) < 2:
            raise CuratorError(
                f"duplicate_hint[{index}] must cite at least two known assets"
            )

    return _result(
        provider_name=provider.name,
        request=request,
        advice=advice,
        ai_called=True,
        alternative_candidate_refs=refs,
    )


def run_adapter_analysis(
    root: Path,
    provider: LibraryCuratorProvider,
    *,
    capability_id: str,
) -> dict[str, object]:
    """Ask for adapter suggestions for known candidates without mutating Library state."""

    request = build_request(
        root,
        task="suggest_adapters",
        capability_id=capability_id,
    )
    refs = _asset_refs(request)

    if not refs:
        deterministic = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [],
        }
        advice = verify_response(request, deterministic)
        return _result(
            provider_name="deterministic-core:no-candidates",
            request=request,
            advice=advice,
            ai_called=False,
            alternative_candidate_refs=[],
        )

    raw = provider.advise(request)
    advice = verify_response(request, raw)
    recommendations = advice.get("recommendations")
    if not isinstance(recommendations, list):
        raise CuratorError("adapter analysis advice is invalid")

    for index, item in enumerate(recommendations):
        if not isinstance(item, dict) or item.get("type") != "adapter_hint":
            raise CuratorError(
                "adapter analysis accepts only adapter_hint recommendations"
            )
        cited = item.get("asset_refs")
        suggestions = item.get("adapter_suggestions")
        if not isinstance(cited, list) or not cited:
            raise CuratorError(
                f"adapter_hint[{index}] must cite at least one known asset"
            )
        if not isinstance(suggestions, list) or not suggestions:
            raise CuratorError(
                f"adapter_hint[{index}] must contain adapter_suggestions"
            )

    return _result(
        provider_name=provider.name,
        request=request,
        advice=advice,
        ai_called=True,
        alternative_candidate_refs=refs,
    )
