"""Read-only source analysis of new Cantiere code for real Library reuse.

Never execute Cantiere code, convert observations into certified manifests, or
modify Researcher queues/claims. Compare committed Cantiere source at pinned
SHAs and retain observations even when a file is not reusable. Subsequent runs
resume at the last fully examined Cantiere head; no silent cursor advancement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "catalog/cantiere-code-reuse-ledger.json"
REPO = "pilialvu75-hue/Ai-orchestrator-riserva"
API = f"https://api.github.com/repos/{REPO}"
RAW = f"https://raw.githubusercontent.com/{REPO}"
SCHEMA = "ai-orchestrator.cantiere-code-reuse-ledger.v1"
EXTENSIONS = {".dart", ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx",
              ".kt", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs",
              ".swift", ".sh"}
MAX_CHANGED_CODE = 100
MAX_FILE_BYTES = 256 * 1024
MAX_LEDGER_RECORDS = 50000
COMMIT = re.compile(r"[a-f0-9]{40}\Z")
SYMBOL = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:final\s+|abstract\s+|sealed\s+)?"
    r"(?:class|enum|mixin|interface|def|function|typedef|struct)\s+([A-Za-z_]\w*)"
)


class HarvestError(ValueError):
    pass


def _request(url: str, *, max_bytes: int = 3 * 1024 * 1024) -> bytes:
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "aivexus-cantiere-code-harvest/1"})
    with urllib.request.urlopen(req, timeout=20) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HarvestError(f"oversized source or API response: {url}")
    return content


def _get_json(url: str) -> dict:
    decoded = json.loads(_request(url))
    if not isinstance(decoded, dict):
        raise HarvestError("GitHub API returned a non-object")
    return decoded


def _get_bytes(url: str) -> bytes:
    return _request(url, max_bytes=MAX_FILE_BYTES)


def _pin(raw: object) -> str:
    value = str(raw).lower()
    if not COMMIT.fullmatch(value):
        raise HarvestError(f"invalid immutable commit SHA: {value!r}")
    return value


def _safe_source_path(name: str) -> str:
    if (not name or len(name) > 400 or name.startswith("/") or
            "\\" in name or ":" in name or "\x00" in name or
            any(p in ("", ".", "..") for p in name.split("/"))):
        raise HarvestError(f"unsafe source path: {name!r}")
    return name


def _is_test(name: str) -> bool:
    parts = name.lower().split("/")
    final = parts[-1]
    return ("test" in parts or "tests" in parts or final.endswith("_test.dart")
            or final.startswith("test_") or final.endswith(".test.js")
            or final.endswith(".spec.ts"))


def _capability_hint(name: str) -> str:
    value = name.lower()
    for marker, capability in (
        ("diagnostic", "diagnostics.logging"),
        ("inference", "ai.local_inference"),
        ("library", "library.integration"),
        ("workspace", "builder.workspace"),
        ("update", "release.update_manager"),
        ("search", "network.search"),
        ("storage", "storage.local_db"),
        ("voice", "voice.audio"),
    ):
        if marker in value:
            return capability
    return "utility.reuse"


def analyse_code(*, path: str, content: bytes, commit: str,
                 blob_sha: str | None = None) -> dict[str, object]:
    _safe_source_path(path)
    if len(content) > MAX_FILE_BYTES:
        raise HarvestError("code file exceeds source-analysis size limit")
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError:
        return {"path": path, "source_commit": commit,
                "blob_sha": blob_sha, "classification": "non_utf8_review",
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "module_status": "not_materialized"}
    symbols = list(dict.fromkeys(SYMBOL.findall(source)))[:20]
    lower = path.lower()
    excluded = ("/generated/" in f"/{lower}" or
                "/third_party/" in f"/{lower}" or
                "/vendor/" in f"/{lower}" or lower.endswith(".g.dart") or
                lower.endswith(".freezed.dart"))
    if excluded:
        label = "generated_or_vendor_review"
    elif _is_test(path):
        label = "test_support"
    elif symbols:
        label = "candidate_requires_extraction_and_tests"
    else:
        label = "app_bound_or_helper_review"
    return {
        "path": path, "source_commit": commit, "blob_sha": blob_sha,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "source_bytes": len(content), "symbols": symbols,
        "import_count": len(re.findall(
            r"(?m)^\s*(?:import|from|require\(|#include)\b", source)),
        "capability_hint": _capability_hint(path),
        "classification": label,
        "module_status": "not_materialized",
        "tested": False, "certified": False,
    }


def run(root: Path = ROOT, *, api_get=_get_json, raw_get=_get_bytes) -> dict:
    state_path = root / "catalog/cantiere-code-reuse-ledger.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema") != SCHEMA or state.get("source_repository") != REPO:
            raise HarvestError("unexpected Cantiere harvest cursor schema")
    else:
        state = {"schema": SCHEMA, "source_repository": REPO,
                 "last_scanned_sha": None, "observations": []}
    head_meta = api_get(f"{API}/commits/main")
    head = _pin(head_meta.get("sha"))
    previous = state.get("last_scanned_sha")
    if previous == head:
        return {"result": "unchanged", "source_head": head, "new_code_files": 0}
    if previous:
        base = _pin(previous)
    else:
        parents = head_meta.get("parents") or []
        if not parents:
            raise HarvestError("no baseline parent commit available; manual baseline required")
        base = _pin(parents[0].get("sha"))
    compare = api_get(f"{API}/compare/{base}...{head}")
    if compare.get("status") not in ("ahead", "identical"):
        raise HarvestError("non-fast-forward Cantiere history; cursor retained")
    if int(compare.get("ahead_by", 0)) > 250:
        raise HarvestError("too many Cantiere commits for bounded diff; cursor retained")
    changes = compare.get("files")
    if not isinstance(changes, list) or len(changes) >= 300:
        raise HarvestError("GitHub compare file list truncated; cursor retained")
    source_changes = [
        x for x in changes
        if isinstance(x, dict) and
        Path(str(x.get("filename", ""))).suffix.lower() in EXTENSIONS
    ]
    if len(source_changes) > MAX_CHANGED_CODE:
        raise HarvestError("too many modified source files; cursor retained")
    previous_records = state["observations"]
    if not isinstance(previous_records, list):
        raise HarvestError("invalid prior source analysis history")
    if len(previous_records) + len(source_changes) > MAX_LEDGER_RECORDS:
        raise HarvestError("Cantiere reuse ledger capacity exceeded; cursor retained")
    new_records = []
    for item in source_changes:
        filename = _safe_source_path(str(item.get("filename") or ""))
        status = item.get("status")
        if status == "removed":
            row = {"path": filename, "source_commit": head,
                   "classification": "removed_source", "module_status": "not_materialized"}
        else:
            encoded_path = "/".join(urllib.parse.quote(x, safe="")
                                    for x in filename.split("/"))
            source = raw_get(f"{RAW}/{head}/{encoded_path}")
            row = analyse_code(path=filename, content=source, commit=head,
                               blob_sha=item.get("sha"))
        new_records.append(row)
    # Keep every observation, even if it is not a module candidate.
    state["observations"] = previous_records + new_records
    state["last_scanned_sha"] = head
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    return {
        "result": "analysed", "base": base, "source_head": head,
        "new_code_files": len(new_records),
        "new_candidates": sum(x.get("classification") ==
                              "candidate_requires_extraction_and_tests"
                              for x in new_records),
        "total_observations": len(state["observations"]),
        "modules_created": 0,
        "note": "Code analysis only; module extraction, tests and Library admission remain distinct.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.root), indent=2, sort_keys=True))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(json.dumps({"result": "blocked", "reason": str(exc),
                          "cursor_advanced": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
