from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from library_package import PackageError, build_package
from library_experimental import export_experimental_packages
from library_pipeline import (
    AssetRef,
    PipelineError,
    load_json,
    manifest_path,
    promote,
    transition_intake,
    validate_ref,
)
from library_resolver import export_snapshot


class AutopilotError(Exception):
    pass


def _discover(root: Path) -> list[AssetRef]:
    intake = root / "intake"
    if not intake.exists():
        return []
    refs: list[AssetRef] = []
    for manifest in sorted(intake.glob("*/*/manifest.json")):
        try:
            relative = manifest.relative_to(intake)
        except ValueError:
            continue
        if len(relative.parts) != 3:
            continue
        ref = AssetRef(relative.parts[0], relative.parts[1])
        try:
            validate_ref(ref)
        except PipelineError:
            continue
        refs.append(ref)
    return refs


def _advance_all(root: Path, ref: AssetRef) -> dict[str, object]:
    path = manifest_path(root, "intake", ref)
    if not path.is_file():
        raise AutopilotError(f"missing intake manifest: {path}")
    manifest = load_json(path)
    status = str(manifest.get("status") or "")
    transitions = {
        "discovered": ("quarantined", "normalized", "tested"),
        "quarantined": ("normalized", "tested"),
        "normalized": ("tested",),
        "tested": (),
    }
    targets = transitions.get(status)
    if targets is None:
        raise AutopilotError(f"unsupported intake status: {status!r}")
    for target in targets:
        transition_intake(root, ref, target)
    return promote(root, ref)


def process_one(root: Path, ref: AssetRef) -> dict[str, object]:
    source = root / "intake" / ref.asset_id / ref.version
    if not source.is_dir():
        return {
            "asset": f"{ref.asset_id}@{ref.version}",
            "result": "skipped",
            "reason": "missing-intake-directory",
        }

    backup_parent = Path(tempfile.mkdtemp(prefix="library-autopilot-"))
    backup = backup_parent / "asset"
    shutil.copytree(source, backup)
    try:
        result = _advance_all(root, ref)
        return {
            "asset": f"{ref.asset_id}@{ref.version}",
            "result": str(result.get("result") or "promoted"),
        }
    except (PipelineError, AutopilotError, OSError, ValueError) as exc:
        if source.exists():
            shutil.rmtree(source)
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup, source)
        return {
            "asset": f"{ref.asset_id}@{ref.version}",
            "result": "blocked",
            "reason": str(exc),
        }
    finally:
        shutil.rmtree(backup_parent, ignore_errors=True)


def refresh_consumption_exports(root: Path) -> dict[str, object]:
    """Persist the exact resolver snapshot and packages consumed by Cantiere."""
    snapshot_path = root / "catalog" / "offline-snapshot.json"
    snapshot_result = export_snapshot(root, snapshot_path)
    snapshot = load_json(snapshot_path)

    packages_root = root / "packages"
    if packages_root.exists():
        shutil.rmtree(packages_root)
    packages_root.mkdir(parents=True, exist_ok=True)

    catalog = load_json(root / "catalog" / "index.json")
    rows: list[dict[str, object]] = []
    for entry in sorted(
        (item for item in catalog.get("assets", []) if isinstance(item, dict)),
        key=lambda item: (str(item.get("id")), str(item.get("version"))),
    ):
        availability = str(entry.get("availability") or "active")
        if availability == "revoked" or entry.get("status") != "certified":
            continue
        asset_id = str(entry.get("id") or "")
        version = str(entry.get("version") or "")
        try:
            envelope = build_package(
                root,
                asset_id,
                version,
                include_deprecated=availability == "deprecated",
            )
        except PackageError as exc:
            raise AutopilotError(
                f"cannot export certified package {asset_id}@{version}: {exc}"
            ) from exc
        relative = Path(asset_id) / version / "package.json"
        output = packages_root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        package = envelope.get("package") or {}
        integrity = package.get("integrity") or {}
        rows.append(
            {
                "pin": f"{asset_id}@{version}",
                "path": f"packages/{relative.as_posix()}",
                "package_sha256": envelope.get("package_sha256"),
                "module_tree_sha256": integrity.get("module_tree_sha256"),
            }
        )

    index = {
        "schema": "ai-orchestrator.library-package-index.v1",
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "packages": rows,
    }
    (packages_root / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Separately export already tested, locally authored source for isolated
    # Cantiere experiments. Never promote it to the certified catalog or
    # declare licenses, runtime safety or reviewer approval.
    experimental = export_experimental_packages(root)
    return {
        "snapshot_sha256": snapshot_result["snapshot_sha256"],
        "package_count": len(rows),
        "sandbox_preview_count": experimental["count"],
        "sandbox_preview_blocked": experimental["blocked"],
    }


def run(root: Path) -> dict[str, object]:
    resolved = root.resolve()
    results = [process_one(resolved, ref) for ref in _discover(resolved)]
    promoted = sum(
        1
        for item in results
        if item["result"] in {"promoted", "already_promoted"}
    )
    blocked = sum(1 for item in results if item["result"] == "blocked")
    exports = refresh_consumption_exports(resolved)
    return {
        "schema": "ai-orchestrator.library-autopilot-report.v1",
        "processed": len(results),
        "promoted": promoted,
        "blocked": blocked,
        "exports": exports,
        "results": results,
    }


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed Module Library intake certification autopilot"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = run(args.root)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
