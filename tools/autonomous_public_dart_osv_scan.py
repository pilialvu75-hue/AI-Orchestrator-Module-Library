#!/usr/bin/env python3
"""Independent advisory check: evidence only, never certification.

Uses OSV's public API; network errors fail closed. It does not mark any
candidate security-reviewed and cannot issue certification signatures.
"""
import argparse
import datetime as dt
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path


def scan(request, timeout=20):
    if request.get("status") != "INDEPENDENT_REVIEW_REQUIRED":
        raise ValueError("expected unsigned review request")
    inventory = request["dependency_inventory"]["cyclonedx_sbom"]
    components = inventory["components"]
    if not isinstance(components, list):
        raise ValueError("invalid SBOM components")
    results = []
    scanned_purls = set()
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("invalid SBOM component")
        purl = component.get("purl")
        if purl is None and isinstance(component.get("bom-ref"), str):
            ref = component["bom-ref"]
            if (ref.startswith("pkg:generic/aivexus_external_")
                    and component.get("name") == ref.removeprefix("pkg:generic/").split("@")[0]
                    and ref.endswith("@" + str(component.get("version", "")))
                    and component.get("version")):
                continue
        if not isinstance(purl, str):
            raise ValueError("SBOM component missing package identity")
        if purl.startswith("pkg:generic/aivexus_external_"):
            continue  # local adapter, not an upstream Pub release
        if not purl.startswith("pkg:pub/"):
            raise ValueError("unsupported SBOM package ecosystem")
        if purl in scanned_purls:
            raise ValueError("duplicate SBOM package identity")
        scanned_purls.add(purl)
        if purl.count("@") != 1:
            raise ValueError("invalid pub package identity")
        name, version = purl.removeprefix("pkg:pub/").rsplit("@", 1)
        if component.get("name") != name or component.get("version") != version:
            raise ValueError("SBOM package identity mismatch")
        if not name or not version:
            raise ValueError("invalid pub package identity")
        payload = json.dumps({"package": {"ecosystem": "Pub", "name": name},
                              "version": version}).encode()
        req = urllib.request.Request("https://api.osv.dev/v1/query", data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("vulns", []), list):
            raise ValueError("invalid OSV advisory response")
        vulns = data.get("vulns", [])
        if any(not isinstance(v, dict) or not isinstance(v.get("id"), str)
               or not v["id"] for v in vulns):
            raise ValueError("invalid OSV vulnerability identity")
        results.append({"package": name, "version": version,
                        "vulnerability_ids": sorted(v["id"] for v in vulns)})
    if not results:
        raise ValueError("no verifiable public package to scan")
    return {"schema": "aivexus.library.osv-advisory-evidence.v1",
            "asset_id": request["asset_id"],
            "source_payload_sha256": request["source"]["payload_tree_sha256"],
            "review_request_sha256": hashlib.sha256(
                json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "scanned_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "provider": "OSV", "endpoint": "https://api.osv.dev/v1/query",
            "packages": results,
            "advisory_scan_completed": True,
            "vulnerabilities_found": sum(len(p["vulnerability_ids"]) for p in results),
            "security_reviewed": False, "certification_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.requests.read_text(encoding="utf-8"))
    if not source.get("requests"):
        raise ValueError("no independent review requests: OSV evidence cannot be empty")
    reports = [scan(item) for item in source["requests"]]
    result = {"schema": "aivexus.library.osv-advisory-collection.v1",
              "reports": reports, "count": len(reports),
              "security_reviewed": False, "certification_authorized": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"scanned": len(reports), "certification_authorized": False}))


if __name__ == "__main__":
    main()
