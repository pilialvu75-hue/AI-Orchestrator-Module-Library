from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from library_pipeline import (
    AssetRef,
    PipelineError,
    load_json,
    manifest_path,
    promote,
    transition_intake,
    validate_ref,
)


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
        # Any failed gate restores the exact intake state that existed before
        # this asset was evaluated. A failed candidate is never left halfway
        # through the lifecycle by the autopilot.
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


def run(root: Path) -> dict[str, object]:
    resolved = root.resolve()
    results = [process_one(resolved, ref) for ref in _discover(resolved)]
    promoted = sum(1 for item in results if item["result"] in {"promoted", "already_promoted"})
    blocked = sum(1 for item in results if item["result"] == "blocked")
    return {
        "schema": "ai-orchestrator.library-autopilot-report.v1",
        "processed": len(results),
        "promoted": promoted,
        "blocked": blocked,
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
    # Blocked candidates are an expected quarantine outcome, not an automation
    # failure. CI validation still decides whether the resulting repository is
    # internally consistent.
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
