from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PRIORITY = {"high": 0, "medium": 1, "low": 2}
SOURCE_PRIORITY = {"high": 0, "medium": 1, "low": 2}
KIND = {
    "module": "module",
    "component": "component",
    "integration_bundle": "integration_bundle",
    "project_template": "project_template",
}


def _git(repo: str, *args: str) -> str:
    return subprocess.check_output(
        ["git", "ls-remote", f"https://github.com/{repo}.git", *args],
        text=True,
        timeout=30,
    ).strip()


def _head_sha(repo: str) -> str:
    rows = _git(repo, "HEAD").splitlines()
    if len(rows) != 1:
        raise RuntimeError(f"cannot resolve immutable HEAD for {repo}")
    sha = rows[0].split()[0].lower()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise RuntimeError(f"invalid upstream SHA for {repo}")
    return sha


def _slug(repo: str) -> str:
    return repo.split("/", 1)[1].lower().replace("_", "-").replace(".", "-")


def select_candidate(root: Path) -> dict[str, object] | None:
    needs = json.loads((root / "catalog/needs.json").read_text(encoding="utf-8"))
    sources = json.loads(
        (root / ".airlab/first-party-sources.json").read_text(encoding="utf-8")
    )
    existing = {
        p.parent.parent.name
        for base in ("intake", "modules")
        for p in (root / base).glob("*/*/manifest.json")
    }

    wanted = sorted(
        (x for x in needs["items"] if x.get("status") == "needed"),
        key=lambda x: (PRIORITY.get(x.get("priority"), 99), x["capability_id"]),
    )
    for need in wanted:
        capability = need["capability_id"]
        candidates = []
        for source in sources["sources"]:
            for candidate in source.get("candidates", []):
                if candidate.get("capability_id") != capability:
                    continue
                asset_id = f"{capability}.firstparty.{_slug(source['repository'])}"
                if asset_id in existing:
                    continue
                candidates.append((SOURCE_PRIORITY.get(source.get("priority"), 99), source, candidate, asset_id))
        if candidates:
            _, source, candidate, asset_id = sorted(candidates, key=lambda x: (x[0], x[1]["repository"], x[2]["component_path"]))[0]
            return {"need": need, "source": source, "candidate": candidate, "asset_id": asset_id}
    return None


def materialize(root: Path, selected: dict[str, object]) -> Path:
    need = selected["need"]
    source = selected["source"]
    candidate = selected["candidate"]
    asset_id = selected["asset_id"]
    repo = source["repository"]
    sha = str(source.get("source_commit") or "").lower()
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        sha = _head_sha(repo)
    version = "0.1.0"
    out = root / "intake" / asset_id / version
    out.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    capability = need["capability_id"]
    component = candidate["component_path"]
    manifest = {
        "id": asset_id,
        "name": f"{repo.split('/')[-1]}:{component}",
        "version": version,
        "kind": KIND[candidate["kind"]],
        "description": f"Autonomously discovered first-party candidate for {capability}.",
        "status": "discovered",
        "capabilities": [capability],
        "platforms": need.get("targets", []),
        "frameworks": [],
        "languages": [],
        "entry_paths": [component],
        "tags": [capability, "researcher-candidate", "first-party"],
        "payload": {
            "type": "upstream_reference",
            "path": None,
            "sha256": None,
            "upstream_repository": f"https://github.com/{repo}",
            "upstream_commit": sha,
        },
        "provenance": {
            "origin": "researcher",
            "source_repository": f"https://github.com/{repo}",
            "source_commit": sha,
            "source_tag": None,
            "source_project_id": repo,
            "source_task_id": f"autonomous-first-party:{capability}:{sha}",
            "retrieved_at": now,
            "license": "NOASSERTION",
            "license_file": None,
        },
        "connector": {
            "standard": "ai-orchestrator-lego",
            "standard_version": "1.0.0",
            "integration_mode": "adapter",
            "provides": [{"capability_id": capability, "contract_id": f"{capability}.v1", "contract_version": "1.0"}],
            "requires": [],
            "adapters": [],
            "configuration_schema": None,
            "healthcheck": {"type": "none", "path": None},
        },
        "integration": {
            "adaptation_allowed": True,
            "estimated_effort": "unknown",
            "adapter_notes": "Researcher discovery only; certification must establish license, security and target compatibility.",
            "known_constraints": ["license unresolved at discovery; fail closed until trusted evidence establishes it"],
        },
        "validation": {"score": 0.0, "tests_passed": False, "test_report": None, "validated_at": None, "validated_on": []},
        "security": {"reviewed": False, "reviewed_at": None, "known_vulnerabilities": 0, "review_report": None, "sbom": None, "notes": "Not yet reviewed."},
        "quality": {"reuse_count": 0, "successful_integrations": 0, "failed_integrations": 0, "last_used_at": None},
        "deprecation": {"reason": None, "replacement": None},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    selected = select_candidate(root)
    if selected is None:
        print(json.dumps({"created": False, "reason": "no_eligible_first_party_candidate"}))
        return 0
    path = materialize(root, selected)
    print(json.dumps({"created": True, "path": str(path.relative_to(root)), "capability": selected["need"]["capability_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
