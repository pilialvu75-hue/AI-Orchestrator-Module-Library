"""Discover a real Dart package from an upstream repository, not a fixed package list.

This is an untrusted candidate acquisition stage, not an admission or certification.
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path

REPO = "dart-lang/core"
API = "https://api.github.com/repos/" + REPO
SAFE = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                "User-Agent": "AIVEXUS-Library-Discovery"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def discover():
    repo = get(API)
    branch = repo["default_branch"]
    ref = get(API + "/branches/" + branch)
    sha = ref["commit"]["sha"]
    tree = get(API + "/git/trees/" + sha + "?recursive=1")
    if tree.get("truncated"):
        raise ValueError("upstream tree is incomplete")
    paths = {x["path"] for x in tree["tree"] if x.get("type") == "blob"}
    packages = sorted({p.split("/")[1] for p in paths
                       if p.startswith("pkgs/") and p.endswith("/pubspec.yaml")
                       and len(p.split("/")) == 3 and SAFE.fullmatch(p.split("/")[1])})
    if not packages:
        raise ValueError("no upstream Dart packages discovered")
    return {"schema": "aivexus.library.external-dart-discovery.v1",
            "repository": "https://github.com/" + REPO,
            "source_commit": sha,
            "candidates": [{"package": p, "pubspec_path": "pkgs/" + p + "/pubspec.yaml",
                            "state": "DISCOVERED_UNTESTED"} for p in packages],
            "candidate_count": len(packages), "certification_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = discover()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"candidate_count": result["candidate_count"],
                      "source_commit": result["source_commit"]}))
