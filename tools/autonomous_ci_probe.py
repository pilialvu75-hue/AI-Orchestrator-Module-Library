"""Read-only GitHub API probe for independent CI evidence.

Intended for a protected default-branch workflow with contents:read and
checks:read. Never consumes worker-supplied API responses as authority.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from tools.autonomous_ci_verifier import verify_pr_checks


def fetch_json(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "airlab-autonomous-ci-probe",
        })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def probe(repository: str, pr_number: int, required_names: list[str], token: str) -> dict:
    if not token:
        raise ValueError("GitHub token missing")
    if repository.count("/") != 1 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/" for c in repository):
        raise ValueError("invalid repository")
    if not isinstance(pr_number, int) or pr_number < 1:
        raise ValueError("invalid PR number")
    base = f"https://api.github.com/repos/{repository}"
    pr = fetch_json(f"{base}/pulls/{pr_number}", token)
    if pr.get("number") is not None and pr["number"] != pr_number:
        raise ValueError("PR number mismatch")
    if (pr.get("base") or {}).get("repo") is not None:
        if ((pr["base"]["repo"] or {}).get("full_name")) != repository:
            raise ValueError("PR base repository mismatch")
    head_sha = (pr.get("head") or {}).get("sha")
    if not isinstance(head_sha, str) or len(head_sha) != 40 or any(c not in "0123456789abcdef" for c in head_sha):
        raise ValueError("invalid PR head")
    response = fetch_json(f"{base}/commits/{head_sha}/check-runs?per_page=100", token)
    if response.get("total_count", 0) > 100:
        raise ValueError("check results exceed one page; refuse incomplete evidence")
    return verify_pr_checks(
        pr=pr, checks=response.get("check_runs", []), repository=repository,
        expected_head_sha=head_sha, required_check_names=required_names,
    )


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: python -m tools.autonomous_ci_probe OWNER/REPO PR_NUMBER CHECK_NAME...", file=sys.stderr)
        return 2
    try:
        result = probe(sys.argv[1], int(sys.argv[2]), sys.argv[3:], os.environ.get("GITHUB_TOKEN", ""))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, urllib.error.URLError, TimeoutError) as exc:
        print(f"CI probe refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
