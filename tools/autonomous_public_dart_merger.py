"""Protected Library control-plane merger for validated Researcher sandbox intake.

Runs only trusted main code. Does not checkout or execute PR source. Requires
two completed independent GitHub Actions checks at the exact immutable PR head.
Only the isolated, unapproved source sandbox may be merged automatically.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

REPO = "pilialvu75-hue/AI-Orchestrator-Module-Library"
HEAD = re.compile(r"researcher/public-dart-(path|characters|fixnum)$")
REQUIRED = {
    "Validate Module Library",
    "Library isolated verification of Researcher public Dart intake",
}


def candidate(pr: dict, files: list[dict]) -> str | None:
    """Return package only for a strictly scoped same-repository automation PR."""
    branch = (pr.get("head") or {}).get("ref", "")
    match = HEAD.fullmatch(branch)
    if not match:
        return None
    pkg = match[1]
    head = pr.get("head") or {}
    repo = head.get("repo") or {}
    if (repo.get("full_name") != REPO
            or (pr.get("base") or {}).get("ref") != "main"
            or pr.get("state") != "open"
            or pr.get("mergeable") is not True
            or not pr.get("title", "").startswith(
                "Researcher autonomous source: " + pkg + " (sandbox only, not certified)")):
        return None
    if not files or len(files) > 400:
        return None
    prefix = "sandbox/researcher_public_dart/" + pkg + "/"
    paths = {row.get("filename") for row in files}
    if (prefix + "metadata.json") not in paths:
        return None
    if any(not isinstance(path, str) or not path.startswith(prefix)
           or ".." in path.split("/") for path in paths):
        return None
    if any(row.get("status") not in ("added", "modified") for row in files):
        return None
    return pkg


def has_required_checks(runs: list[dict], sha: str) -> bool:
    """Only completed successful PR-triggered validations of the SAME commit."""
    passed = {
        row.get("name")
        for row in runs
        if (row.get("head_sha") == sha and row.get("event") == "pull_request"
            and row.get("status") == "completed" and row.get("conclusion") == "success")
    }
    return REQUIRED <= passed


def request(method: str, path: str, data: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("protected Library token missing")
    url = "https://api.github.com/repos/" + REPO + "/" + path
    body = None if data is None else json.dumps(data).encode()
    headers = {"Accept": "application/vnd.github+json",
               "Authorization": "Bearer " + token,
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "Aivexus-Library-Protected-Sandbox-Merge"}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError("GitHub repository request failed: " + str(getattr(exc, "code", type(exc).__name__))) from exc


def list_files(number: int) -> list[dict]:
    result: list[dict] = []
    for page in range(1, 6):
        rows = request("GET", f"pulls/{number}/files?per_page=100&page={page}")
        if not isinstance(rows, list):
            raise ValueError("invalid PR file response")
        result.extend(rows)
        if len(result) > 400:
            raise ValueError("sandbox PR exceeds bounded change set")
        if len(rows) < 100:
            return result
    raise ValueError("PR changed files exceed maximum pages")


def run() -> dict:
    pending = request("GET", "pulls?state=open&base=main&per_page=100")
    if not isinstance(pending, list):
        raise ValueError("GitHub returned invalid PR list")
    report: dict = {
        "schema": "aivexus.library.protected-automerge-public-source.v1",
        "examined": 0, "merged": [], "deferred": [],
        "security_certified": False, "production_installation": False,
    }
    for row in pending:
        branch = (row.get("head") or {}).get("ref", "")
        if not HEAD.fullmatch(branch):
            continue
        number = row.get("number")
        if type(number) is not int or number < 1:
            continue
        report["examined"] += 1
        # Re-fetch from GitHub: a list snapshot cannot authorize a merge.
        current = request("GET", f"pulls/{number}")
        files = list_files(number)
        pkg = candidate(current, files)
        if pkg is None:
            report["deferred"].append({"number": number, "reason": "unsafe_scope_or_mergeability"})
            continue
        sha = current["head"]["sha"]
        runs = request("GET", "actions/runs?head_sha=" + urllib.parse.quote(sha) + "&per_page=100")
        workflows = runs.get("workflow_runs", [])
        if not isinstance(workflows, list) or not has_required_checks(workflows, sha):
            report["deferred"].append({"number": number, "reason": "exact_head_checks_incomplete"})
            continue
        # GitHub applies branch protection and rejects conflicts; never override.
        reply = request("PUT", f"pulls/{number}/merge", {
            "sha": sha, "merge_method": "squash",
            "commit_title": f"library: admit independently tested Researcher public {pkg} source to sandbox",
        })
        if reply.get("merged") is True:
            report["merged"].append({"number": number, "package": pkg, "sha": sha})
        else:
            report["deferred"].append({"number": number, "reason": "github_merge_rejected"})
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, sort_keys=True))
