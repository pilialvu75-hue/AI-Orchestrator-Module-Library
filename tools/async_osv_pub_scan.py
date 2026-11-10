"""Query OSV for resolved pub.dev packages; fail closed on missing evidence."""
import argparse
import json
import urllib.request
from pathlib import Path


def scan(graph, query):
    packages = graph.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("resolved Dart package graph missing")
    items = []
    for package in packages:
        name, version = package.get("name"), package.get("version")
        if not isinstance(name, str) or not isinstance(version, str) or not version:
            raise ValueError("resolved package lacks name or version")
        if package.get("kind") == "root":
            continue
        if package.get("source") == "path":
            # Vendored async is pinned to source, but OSV version still queried.
            pass
        items.append({"package": {"ecosystem": "Pub", "name": name},
                      "version": version})
    if not items:
        raise ValueError("no dependency packages available for OSV")
    payload = json.dumps({"queries": items}).encode()
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch", data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "aivexus-library-review/1"},
        method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    matches = result.get("results")
    if not isinstance(matches, list) or len(matches) != len(items):
        raise ValueError("OSV returned incomplete result set")
    findings = []
    for item, match in zip(items, matches):
        if not isinstance(match, dict):
            raise ValueError("OSV result item invalid")
        vulns = match.get("vulns", [])
        if not isinstance(vulns, list):
            raise ValueError("OSV vulnerabilities malformed")
        findings.append({"name": item["package"]["name"], "version": item["version"],
                         "vulnerability_ids": [v["id"] for v in vulns]})
    return {"schema": "aivexus.library.osv-pub-review.v1",
            "source": "https://api.osv.dev/v1/querybatch",
            "queried_packages": len(findings),
            "findings": findings,
            "advisory_scan_completed": True,
            "vulnerabilities_reported": sum(len(f["vulnerability_ids"]) for f in findings),
            "independent_security_reviewed": False,
            "certification_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text())
    result = scan(graph, None)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"queried_packages": result["queried_packages"],
                      "vulnerabilities_reported": result["vulnerabilities_reported"],
                      "certification_authorized": False}))


if __name__ == "__main__":
    main()
