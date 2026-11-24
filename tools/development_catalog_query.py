"""Read-only lookup of independently tested internal development packages."""
import argparse
import hashlib
import json
from pathlib import Path

def query(root, capability, contract, target):
    root = Path(root).resolve()
    index = json.loads((root / "packages/development-index.json").read_text(encoding="utf-8"))
    evidence_path = root / "packages/development-platform-evidence.json"
    evidence = set()
    if evidence_path.exists():
        ledger = json.loads(evidence_path.read_text(encoding="utf-8"))
        if ledger.get("schema") != "aivexus.development-platform-evidence.v1":
            raise ValueError("Invalid platform evidence schema")
        for row in ledger["records"]:
            if (row["target"] not in {"linux", "windows", "macos"}
                    or type(row["run_id"]) is not int or row["run_id"] <= 0
                    or type(row["job_id"]) is not int or row["job_id"] <= 0):
                raise ValueError("Invalid platform evidence record")
            key = (row["pin"], row["package_sha256"], row["target"])
            if key in evidence:
                raise ValueError("Duplicate platform evidence")
            evidence.add(key)
    results = []
    for entry in index["packages"]:
        if (entry.get("development_qualified") is not True
                or entry.get("independent_export_consumer") != "PASS"
                or (target not in entry.get("validated_targets", [])
                    and (entry["pin"], entry["package_sha256"], target) not in evidence)):
            continue
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root / "packages"):
            raise ValueError("Package path outside library")
        envelope = json.loads(path.read_text(encoding="utf-8"))
        package = envelope["package"]
        digest = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        if digest != entry["package_sha256"] or digest != envelope["package_sha256"]:
            raise ValueError("Package integrity mismatch")
        if package["pin"] != entry["pin"]:
            raise ValueError("Package pin mismatch")
        if (capability in package["capabilities"] and contract in package["contracts"]
                and (target in package["targets"] or
                     (entry["pin"], digest, target) in evidence)):
            results.append({"pin": entry["pin"], "path": entry["path"],
                            "package_sha256": digest, "target": target,
                            "production_approved": False, "scope": "internal-isolated-evaluation"})
    return sorted(results, key=lambda record: record["pin"])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--capability", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(json.dumps({"candidates": query(args.root, args.capability, args.contract, args.target)}, indent=2))
