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


def _result(
    *,
    provider_name: str,
    request: dict[str, object],
    advice: dict[str, object],
    candidate_count: int,
    ai_called: bool,
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
            "semantic_ranking_complete": True,
            "candidate_count": candidate_count,
            "ai_called": ai_called,
        },
    }


def run_semantic_ranking(
    root: Path,
    provider: LibraryCuratorProvider,
    *,
    capability_id: str,
) -> dict[str, object]:
    request = build_request(
        root,
        task="rank_candidates",
        capability_id=capability_id,
    )
    context = request.get("context")
    if not isinstance(context, dict):
        raise CuratorError("semantic ranking request context is invalid")
    assets = context.get("assets")
    if not isinstance(assets, list):
        raise CuratorError("semantic ranking request assets are invalid")

    candidate_refs = [
        str(asset.get("ref"))
        for asset in assets
        if isinstance(asset, dict) and asset.get("ref")
    ]

    if not candidate_refs:
        deterministic = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "recommendations": [
                {
                    "type": "coverage_gap",
                    "confidence": 1.0,
                    "summary": (
                        f"No Library or intake candidates are available for {capability_id}."
                    ),
                    "asset_refs": [],
                    "capability_ids": [capability_id],
                    "adapter_suggestions": [],
                    "warnings": [
                        "AI call skipped because there are no candidates to rank."
                    ],
                    "ranking_factors": [],
                }
            ],
        }
        advice = verify_response(request, deterministic)
        return _result(
            provider_name="deterministic-core:no-candidates",
            request=request,
            advice=advice,
            candidate_count=0,
            ai_called=False,
        )

    raw = provider.advise(request)
    advice = verify_response(request, raw)
    recommendations = advice.get("recommendations")
    if not isinstance(recommendations, list):
        raise CuratorError("semantic ranking advice is invalid")

    rankings = [
        item
        for item in recommendations
        if isinstance(item, dict) and item.get("type") == "candidate_ranking"
    ]
    if len(rankings) != 1:
        raise CuratorError(
            "semantic ranking requires exactly one candidate_ranking recommendation"
        )

    ranked_refs = rankings[0].get("asset_refs")
    if not isinstance(ranked_refs, list):
        raise CuratorError("semantic ranking asset_refs are invalid")
    if len(ranked_refs) != len(candidate_refs) or set(ranked_refs) != set(candidate_refs):
        raise CuratorError(
            "semantic ranking must cover every supplied candidate exactly once"
        )

    return _result(
        provider_name=provider.name,
        request=request,
        advice=advice,
        candidate_count=len(candidate_refs),
        ai_called=True,
    )
