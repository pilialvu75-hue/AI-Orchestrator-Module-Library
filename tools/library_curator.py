from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Protocol

REQUEST_SCHEMA = "ai-orchestrator.library-curator-request.v1"
RESPONSE_SCHEMA = "ai-orchestrator.library-curator-response.v1"
RESULT_SCHEMA = "ai-orchestrator.library-curator-result.v1"

ALLOWED_TASKS = {
    "coverage",
    "rank_candidates",
    "find_duplicates",
    "suggest_adapters",
    "health_review",
}
ALLOWED_RECOMMENDATION_TYPES = {
    "coverage_gap",
    "candidate_ranking",
    "reuse_recommendation",
    "duplicate_hint",
    "adapter_hint",
    "health_warning",
}


class CuratorError(Exception):
    pass


class LibraryCuratorProvider(Protocol):
    """Provider boundary. Implementations receive sanitized Library context only."""

    @property
    def name(self) -> str: ...

    def advise(self, request: dict[str, object]) -> dict[str, object]: ...


def _load_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CuratorError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CuratorError(f"expected JSON object at {path}")
    return data


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _contracts(manifest: dict[str, object]) -> list[str]:
    connector = manifest.get("connector")
    if not isinstance(connector, dict):
        return []
    provides = connector.get("provides")
    if not isinstance(provides, list):
        return []
    values: set[str] = set()
    for item in provides:
        if isinstance(item, dict):
            contract_id = item.get("contract_id")
            if isinstance(contract_id, str) and contract_id.strip():
                values.add(contract_id)
    return sorted(values)


def _safe_asset_view(
    manifest: dict[str, object],
    *,
    source_area: str,
    availability: str,
) -> dict[str, object]:
    provenance = manifest.get("provenance")
    validation = manifest.get("validation")
    security = manifest.get("security")
    integration = manifest.get("integration")

    provenance = provenance if isinstance(provenance, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    security = security if isinstance(security, dict) else {}
    integration = integration if isinstance(integration, dict) else {}

    asset_id = str(manifest.get("id") or "")
    version = str(manifest.get("version") or "")
    return {
        "ref": f"{asset_id}@{version}",
        "id": asset_id,
        "version": version,
        "source_area": source_area,
        "status": str(manifest.get("status") or ""),
        "availability": availability,
        "kind": str(manifest.get("kind") or ""),
        "description": str(manifest.get("description") or ""),
        "capabilities": sorted(set(_strings(manifest.get("capabilities")))),
        "platforms": sorted(set(_strings(manifest.get("platforms")))),
        "contracts": _contracts(manifest),
        "provenance": {
            "origin": provenance.get("origin"),
            "source_repository": provenance.get("source_repository"),
            "source_commit": provenance.get("source_commit"),
            "license": provenance.get("license"),
        },
        "validation": {
            "score": validation.get("score"),
            "tests_passed": validation.get("tests_passed") is True,
            "validated_on": _strings(validation.get("validated_on")),
        },
        "security": {
            "reviewed": security.get("reviewed") is True,
            "known_vulnerabilities": security.get("known_vulnerabilities"),
        },
        "integration": {
            "estimated_effort": integration.get("estimated_effort"),
            "adaptation_allowed": integration.get("adaptation_allowed") is True,
            "known_constraints": _strings(integration.get("known_constraints")),
        },
    }


def _catalog_availability(root: Path) -> dict[str, str]:
    catalog = _load_json(root / "catalog" / "index.json")
    result: dict[str, str] = {}
    assets = catalog.get("assets")
    if not isinstance(assets, list):
        return result
    for item in assets:
        if not isinstance(item, dict):
            continue
        asset_id = item.get("id")
        version = item.get("version")
        if not isinstance(asset_id, str) or not isinstance(version, str):
            continue
        availability = str(item.get("availability") or "active")
        result[f"{asset_id}@{version}"] = availability
    return result


def _asset_context(root: Path) -> list[dict[str, object]]:
    availability = _catalog_availability(root)
    rows: list[dict[str, object]] = []

    for source_area in ("modules", "intake"):
        base = root / source_area
        if not base.exists():
            continue
        for path in sorted(base.glob("*/*/manifest.json")):
            manifest = _load_json(path)
            asset_id = str(manifest.get("id") or "")
            version = str(manifest.get("version") or "")
            ref = f"{asset_id}@{version}"
            rows.append(
                _safe_asset_view(
                    manifest,
                    source_area=source_area,
                    availability=(
                        availability.get(ref, "active")
                        if source_area == "modules"
                        else "not_certified"
                    ),
                )
            )

    return sorted(rows, key=lambda row: str(row["ref"]))


def _need_context(root: Path) -> list[dict[str, object]]:
    needs = _load_json(root / "catalog" / "needs.json")
    rows = needs.get("items")
    if not isinstance(rows, list):
        raise CuratorError("catalog/needs.json: items must be an array")
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "capability_id": row.get("capability_id"),
                "title": row.get("title"),
                "priority": row.get("priority"),
                "desired_candidates": row.get("desired_candidates"),
                "status": row.get("status"),
                "targets": _strings(row.get("targets")),
            }
        )
    return result


def build_request(
    root: Path,
    *,
    task: str,
    capability_id: str | None = None,
) -> dict[str, object]:
    if task not in ALLOWED_TASKS:
        raise CuratorError(f"unsupported curator task: {task}")

    needs = _need_context(root)
    assets = _asset_context(root)
    known_capabilities = {
        str(item.get("capability_id"))
        for item in needs
        if item.get("capability_id")
    }
    for asset in assets:
        known_capabilities.update(_strings(asset.get("capabilities")))

    if capability_id is not None and capability_id not in known_capabilities:
        raise CuratorError(f"unknown capability_id: {capability_id}")

    if capability_id is not None:
        needs = [
            item for item in needs if item.get("capability_id") == capability_id
        ]
        assets = [
            item
            for item in assets
            if capability_id in _strings(item.get("capabilities"))
        ]

    context = {
        "needs": needs,
        "assets": assets,
    }
    request_seed = {
        "task": task,
        "capability_id": capability_id,
        "context": context,
    }
    request_id = _sha256(request_seed)[:24]
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "task": task,
        "capability_id": capability_id,
        "policy": {
            "advisory_only": True,
            "core_is_authoritative": True,
            "provider_may_mutate_library": False,
            "provider_may_certify": False,
            "provider_may_revoke": False,
        },
        "context": context,
        "context_sha256": _sha256(context),
    }


def _require_exact_keys(
    value: dict[str, object],
    allowed: set[str],
    where: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CuratorError(f"{where}: unsupported fields: {', '.join(unknown)}")


def _validate_string_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CuratorError(f"{where} must be an array of strings")
    values = [item.strip() for item in value if item.strip()]
    if len(values) != len(set(values)):
        raise CuratorError(f"{where} contains duplicates")
    return values


def verify_response(
    request: dict[str, object],
    response: dict[str, object],
) -> dict[str, object]:
    if not isinstance(response, dict):
        raise CuratorError("provider response must be a JSON object")
    _require_exact_keys(
        response,
        {"schema", "request_id", "recommendations"},
        "response",
    )
    if response.get("schema") != RESPONSE_SCHEMA:
        raise CuratorError("provider response schema mismatch")
    if response.get("request_id") != request.get("request_id"):
        raise CuratorError("provider response request_id mismatch")

    context = request.get("context")
    if not isinstance(context, dict):
        raise CuratorError("request context is invalid")
    assets = context.get("assets")
    needs = context.get("needs")
    if not isinstance(assets, list) or not isinstance(needs, list):
        raise CuratorError("request context is incomplete")

    asset_by_ref = {
        str(asset.get("ref")): asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("ref")
    }
    capability_ids = {
        str(item.get("capability_id"))
        for item in needs
        if isinstance(item, dict) and item.get("capability_id")
    }
    for asset in asset_by_ref.values():
        capability_ids.update(_strings(asset.get("capabilities")))

    recommendations = response.get("recommendations")
    if not isinstance(recommendations, list):
        raise CuratorError("recommendations must be an array")

    verified: list[dict[str, object]] = []
    for index, item in enumerate(recommendations):
        where = f"recommendations[{index}]"
        if not isinstance(item, dict):
            raise CuratorError(f"{where} must be an object")
        _require_exact_keys(
            item,
            {
                "type",
                "confidence",
                "summary",
                "asset_refs",
                "capability_ids",
                "adapter_suggestions",
                "warnings",
            },
            where,
        )

        recommendation_type = item.get("type")
        if recommendation_type not in ALLOWED_RECOMMENDATION_TYPES:
            raise CuratorError(f"{where}: unsupported recommendation type")

        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise CuratorError(f"{where}.confidence must be numeric")
        confidence = float(confidence)
        if confidence < 0.0 or confidence > 1.0:
            raise CuratorError(f"{where}.confidence must be between 0 and 1")

        summary = item.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise CuratorError(f"{where}.summary must be non-empty")
        if len(summary) > 1200:
            raise CuratorError(f"{where}.summary is too long")

        refs = _validate_string_list(item.get("asset_refs"), f"{where}.asset_refs")
        unknown_refs = sorted(set(refs) - set(asset_by_ref))
        if unknown_refs:
            raise CuratorError(
                f"{where}: provider cited unknown assets: {', '.join(unknown_refs)}"
            )

        cited_capabilities = _validate_string_list(
            item.get("capability_ids"),
            f"{where}.capability_ids",
        )
        unknown_capabilities = sorted(set(cited_capabilities) - capability_ids)
        if unknown_capabilities:
            raise CuratorError(
                f"{where}: provider cited unknown capabilities: "
                + ", ".join(unknown_capabilities)
            )

        adapter_suggestions = _validate_string_list(
            item.get("adapter_suggestions"),
            f"{where}.adapter_suggestions",
        )
        warnings = _validate_string_list(item.get("warnings"), f"{where}.warnings")

        if recommendation_type == "reuse_recommendation":
            if not refs:
                raise CuratorError(f"{where}: reuse recommendation requires asset_refs")
            for ref in refs:
                asset = asset_by_ref[ref]
                if (
                    asset.get("source_area") != "modules"
                    or asset.get("status") != "certified"
                    or asset.get("availability") != "active"
                ):
                    raise CuratorError(
                        f"{where}: {ref} is not an active certified Library asset"
                    )

        verified.append(
            {
                "type": recommendation_type,
                "confidence": confidence,
                "summary": summary.strip(),
                "asset_refs": refs,
                "capability_ids": cited_capabilities,
                "adapter_suggestions": adapter_suggestions,
                "warnings": warnings,
            }
        )

    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request["request_id"],
        "recommendations": verified,
    }


def run_curator(
    root: Path,
    provider: LibraryCuratorProvider,
    *,
    task: str,
    capability_id: str | None = None,
) -> dict[str, object]:
    request = build_request(root, task=task, capability_id=capability_id)
    raw = provider.advise(request)
    advice = verify_response(request, raw)
    return {
        "schema": RESULT_SCHEMA,
        "provider": provider.name,
        "request": request,
        "advice": advice,
        "core_verification": {
            "passed": True,
            "advisory_only": True,
            "library_mutated": False,
            "authority": "deterministic-library-core",
        },
    }


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Build sanitized, provider-neutral AI Curator requests"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--task", choices=sorted(ALLOWED_TASKS), required=True)
    parser.add_argument("--capability")
    args = parser.parse_args(argv)

    try:
        request = build_request(
            args.root.resolve(),
            task=args.task,
            capability_id=args.capability,
        )
    except CuratorError as exc:
        print(f"LIBRARY CURATOR FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(request, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
