"""Bounded Cantiere -> Library *source* materializer (never a certification).

Run after a successful pinned Cantiere source harvest. Only a small Python
component from Cantiere tool/ with a matching independently observed test
file can be staged per run. No fetched code is imported, executed, approved,
or published as experimental. Tests + evidence remain separate requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from cantiere_code_reuse_harvest import (
    REPO, SCHEMA, RAW, _get_bytes, _pin, _safe_source_path,
)
from library_source_integrity import payload_tree_sha256

ROOT = Path(__file__).resolve().parents[1]
LEDGER = "catalog/cantiere-code-reuse-ledger.json"
TEMPLATE = "intake/library.integration.firstparty.cantiere_preview_reader/0.1.0/manifest.json"
_NAME = re.compile(r"[a-z][a-z0-9_]{3,70}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
MAX_STAGED_PER_RUN = 1


class MaterializationError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise MaterializationError(message)


def _download_observed(row: dict, *, raw_get) -> bytes:
    sha = _pin(row.get("source_commit"))
    path = _safe_source_path(str(row.get("path") or ""))
    expected = row.get("source_sha256")
    _require(isinstance(expected, str) and _HASH.fullmatch(expected) is not None,
             f"missing source SHA-256 for {path}")
    # Every byte is fetched from the exact observed Cantiere commit, not main.
    from urllib.parse import quote
    escaped = "/".join(quote(part, safe="") for part in path.split("/"))
    source = raw_get(f"{RAW}/{sha}/{escaped}")
    _require(isinstance(source, bytes) and 0 < len(source) <= 256 * 1024,
             f"invalid materialized source size: {path}")
    _require(hashlib.sha256(source).hexdigest() == expected,
             f"source hash mismatch for {path}")
    # Parse only; do not import/execute either source or tests.
    import ast
    try:
        ast.parse(source.decode("utf-8"), filename=path)
    except (SyntaxError, UnicodeError) as exc:
        raise MaterializationError(f"not valid UTF-8 Python source: {path}") from exc
    return source


def stage_one(root: Path = ROOT, *, raw_get=_get_bytes) -> dict:
    root = root.resolve()
    state_path = root / LEDGER
    state = json.loads(state_path.read_text(encoding="utf-8"))
    _require(state.get("schema") == SCHEMA and
             state.get("source_repository") == REPO, "invalid Cantiere ledger")
    rows = state.get("observations")
    _require(isinstance(rows, list), "missing Cantiere code observations")
    source_rows = [
        row for row in rows if isinstance(row, dict) and
        row.get("classification") == "candidate_requires_extraction_and_tests" and
        row.get("module_status") == "not_materialized" and
        re.fullmatch(r"tool/[a-z][a-z0-9_]{3,70}\.py",
                     str(row.get("path") or "")) and
        row.get("capability_hint") == "library.integration"
    ]
    source_rows.sort(key=lambda row: (row["source_commit"], row["path"]))
    for source in source_rows:
        path = source["path"]
        stem = Path(path).stem
        if not _NAME.fullmatch(stem):
            continue
        test_path = f"test/tool/test_{stem}.py"
        matching = [
            row for row in rows if isinstance(row, dict) and
            row.get("path") == test_path and
            row.get("source_commit") == source["source_commit"] and
            row.get("classification") == "test_support"
        ]
        if len(matching) != 1:
            continue  # no independently observed exact-commit regression source
        test_row = matching[0]
        asset_id = f"library.integration.firstparty.cantiere_{stem}"
        version = "0.1.0"
        target = root / "intake" / asset_id / version
        if target.exists():
            continue  # never overwrite an active or concurrently staged candidate
        pinned = _pin(source["source_commit"])
        source_bytes = _download_observed(source, raw_get=raw_get)
        test_bytes = _download_observed(test_row, raw_get=raw_get)
        template = json.loads((root / TEMPLATE).read_text(encoding="utf-8"))
        _require(template.get("connector", {}).get("provides", [])[0].get("contract_id") ==
                 "library.integration.v1", "missing sandbox integration contract")
        template["id"] = asset_id
        template["name"] = f"Cantiere reusable Python source: {stem}"
        template["description"] = (
            "Pinned Cantiere source with an accompanying real regression test; "
            "not yet compiled, tested by Library CI or available to Cantiere."
        )
        template["status"] = "discovered"
        template["entry_paths"] = [path]
        template["tags"] = ["cantiere-reuse", "python", "discovered"]
        template["provenance"] = {
            "origin": "built_in",
            "source_repository": f"https://github.com/{REPO}",
            "source_commit": pinned,
            "source_tag": None, "source_project_id": REPO,
            "source_task_id": f"cantiere-harvest:{pinned}:{path}",
            "license": None, "license_file": None, "retrieved_at": None,
        }
        template["validation"] = {
            "score": 0, "tests_passed": False, "test_report": None,
            "validated_at": None, "validated_on": [],
        }
        template["security"] = {
            "reviewed": False, "reviewed_at": None,
            "known_vulnerabilities": None, "sbom": None,
            "review_report": None,
            "notes": "Unreviewed Cantiere source. Do not execute in harvest workflow.",
        }
        template["integration"]["adapter_notes"] = (
            "Source and test are copied byte-for-byte from the observed Cantiere "
            "commit; dependencies, license and platform support require validation."
        )
        template["integration"]["known_constraints"] = [
            "No tests have yet been run on this extracted payload.",
            "No automatically granted runtime privileges or production use.",
            "Distribution license and independent security review unresolved.",
        ]
        template["dependencies"] = [
            {"name": "Python", "version": ">=3.12", "source": "host runtime"},
        ]
        template["quality"] = {
            "reuse_count": 0, "successful_integrations": 0,
            "failed_integrations": 0, "last_used_at": None,
        }
        (root / "intake").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".cantiere-stage-", dir=root / "intake"
        ) as temporary:
            staging = Path(temporary) / "candidate"
            module = staging / "payload" / "src"
            for relative, data in ((path, source_bytes),
                                   (test_path, test_bytes)):
                destination = module / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            template["payload"] = {
                "type": "repository_path",
                "path": "payload/src",
                "sha256": payload_tree_sha256(module),
                "upstream_repository": f"https://github.com/{REPO}",
                "upstream_commit": pinned,
            }
            (staging / "manifest.json").write_text(
                json.dumps(template, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            _require(not target.exists(), "candidate directory already exists")
            os.replace(staging, target)
        source["module_status"] = "source_materialized_needs_tests"
        source["library_pin"] = f"{asset_id}@{version}"
        source["library_payload_sha256"] = template["payload"]["sha256"]
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=state_path.parent,
            prefix=".cantiere-ledger-", delete=False,
        ) as temporary:
            json.dump(state, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temp_path = temporary.name
        os.replace(temp_path, state_path)
        return {
            "staged": 1, "source_commit": pinned,
            "library_pin": source["library_pin"],
            "source_files": [path, test_path],
            "status": "source_materialized_needs_tests",
        }
    return {"staged": 0, "status": "no_new_test_backed_python_candidate"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(stage_one(args.root), indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
