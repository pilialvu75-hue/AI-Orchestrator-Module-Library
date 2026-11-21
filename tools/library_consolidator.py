"""Identify comparable tested modules without deleting or promoting source."""
import json
from pathlib import Path
from collections import defaultdict

def comparison_groups(root: Path) -> dict:
    index = json.loads((root / "packages/experimental-index.json").read_text())
    groups = defaultdict(list)
    for row in index["packages"]:
        package = json.loads((root / row["path"]).read_text())["package"]
        # Capability alone is insufficient: require a shared explicit contract.
        for contract in package.get("contracts", []):
            key = (contract, tuple(sorted(package["capabilities"])),
                   tuple(sorted(package["targets"])))
            groups[key].append({"pin": row["pin"],
                                "package_sha256": row["package_sha256"],
                                "source": package["source"]})
    comparisons = []
    for (contract, capabilities, targets), candidates in sorted(groups.items()):
        if len(candidates) < 2:
            continue
        comparisons.append({"contract": contract, "capabilities": capabilities,
                            "targets": targets, "candidates": candidates,
                            "action": "compare_functional_coverage_and_benchmark",
                            "primary": None, "reserve": None,
                            "pruning_allowed": False})
    return {"schema": "aivexus.library.consolidation-plan.v1",
            "groups": comparisons}

if __name__ == "__main__":
    print(json.dumps(comparison_groups(Path(__file__).resolve().parents[1]), indent=2))
