from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_covered(required: str, certified: set[str]) -> bool:
    required = required.lower()
    certified = {item.lower() for item in certified}
    if required == "desktop":
        return bool(certified & {"desktop", "windows", "linux", "macos"})
    return required in certified


def reconcile(root: Path, *, now: str | None = None) -> dict[str, Any]:
    catalog = _load(root / "catalog" / "index.json")
    sources = [_load(root / "catalog" / "needs.json")]
    extension = root / "catalog" / "needs.platform-extension.json"
    if extension.is_file():
        sources.append(_load(extension))

    merged: dict[str, dict[str, Any]] = {}
    for source in sources:
        for raw in source.get("items", []):
            item = dict(raw)
            cid = str(item["capability_id"])
            if cid in merged:
                existing = merged[cid]
                existing["targets"] = sorted(set(existing["targets"]) | set(item["targets"]))
                existing["desired_candidates"] = max(int(existing["desired_candidates"]), int(item["desired_candidates"]))
            else:
                merged[cid] = item

    coverage: dict[str, dict[str, dict[str, int]]] = {"certified": {}, "adaptable": {}}
    for asset in catalog.get("assets", []):
        status = str(asset.get("status"))
        if asset.get("availability", "active") == "revoked" or status not in {"certified", "tested"}:
            continue
        lane = "certified" if status == "certified" else "adaptable"
        platforms = {str(x).lower() for x in asset.get("platforms", [])}
        for capability in asset.get("capabilities", []):
            cid = str(capability)
            row = coverage[lane].setdefault(cid, {})
            for platform in platforms:
                row[platform] = row.get(platform, 0) + 1

    changed = 0
    for cid, item in merged.items():
        desired = int(item["desired_candidates"])
        counts = coverage["certified"].get(cid, {})
        targets = [str(x).lower() for x in item["targets"]]
        satisfied = all(
            sum(count for platform, count in counts.items() if _target_covered(target, {platform})) >= desired
            for target in targets
        )
        wanted = "satisfied" if satisfied else "needed"
        if item.get("status") not in {"paused"} and item.get("status") != wanted:
            item["status"] = wanted
            changed += 1

    rendered_items = [merged[key] for key in sorted(merged)]
    timestamp = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {"schema_version": 1, "updated_at": timestamp, "items": rendered_items}
    target = root / "catalog" / "needs.json"
    previous = _load(target)
    semantic_changed = previous.get("items") != rendered_items
    if semantic_changed:
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    coverage_result = {
        "schema_version": 1,
        "updated_at": timestamp,
        "certified": coverage["certified"],
        "adaptable": coverage["adaptable"],
    }
    coverage_target = root / "catalog" / "coverage.json"
    previous_coverage = _load(coverage_target) if coverage_target.is_file() else None
    coverage_changed = previous_coverage is None or {
        "certified": previous_coverage.get("certified", {}),
        "adaptable": previous_coverage.get("adaptable", {}),
    } != {
        "certified": coverage_result["certified"],
        "adaptable": coverage_result["adaptable"],
    }
    if coverage_changed:
        coverage_target.write_text(json.dumps(coverage_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "schema": "ai-orchestrator.library-needs-reconcile.v1",
        "semantic_changed": semantic_changed,
        "coverage_changed": coverage_changed,
        "status_changes": changed,
        "needs": len(rendered_items),
        "certified_capabilities": len(coverage["certified"]),
        "adaptable_capabilities": len(coverage["adaptable"]),
        "coverage": coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(reconcile(args.root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
