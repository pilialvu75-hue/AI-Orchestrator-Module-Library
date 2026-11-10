"""Generate a source-bound resolved CycloneDX SBOM for independent review.

No security approval is inferred from a dependency graph or an SBOM.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def build(graph: dict, packet: dict) -> dict:
    packages = graph.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("resolved package graph missing")
    if packet.get("asset_id") != "utility.async_stream_queue.external.dartlang.async":
        raise ValueError("unexpected source-bound candidate")
    source = packet["source"]
    digest = source["payload_tree_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid source digest")
    components = []
    seen = set()
    for item in packages:
        if not isinstance(item, dict):
            raise ValueError("invalid package graph entry")
        name, version = item.get("name"), item.get("version")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError("invalid package name")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?", version):
            raise ValueError("unresolved or invalid package version")
        if name in seen:
            raise ValueError("duplicate package identity")
        seen.add(name)
        components.append({
            "type": "library", "name": name, "version": version,
            "bom-ref": f"pkg:pub/{name}@{version}",
            "purl": f"pkg:pub/{name}@{version}",
        })
    if not {"async", "collection", "meta"}.issubset(seen):
        raise ValueError("required upstream dependencies missing")
    components.sort(key=lambda item: item["name"])
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {
            "type": "library", "name": packet["asset_id"], "version": packet["version"],
            "properties": [
                {"name": "aivexus:source_payload_sha256", "value": digest},
                {"name": "aivexus:source_commit", "value": source["commit"]},
            ],
        }},
        "components": components,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sbom = build(json.loads(args.graph.read_text()), json.loads(args.packet.read_text()))
    args.output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + chr(10))
    print(json.dumps({"resolved_components": len(sbom["components"]),
                      "sbom_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "security_reviewed": False, "certification_authorized": False}))


if __name__ == "__main__":
    main()
