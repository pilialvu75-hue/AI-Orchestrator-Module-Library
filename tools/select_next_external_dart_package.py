"""Select a new upstream candidate without repeating already admitted packages.

Selection is discovery-only; it does not assert tests, security review or admission.
"""
import argparse
import json
from pathlib import Path


def select(discovery, manifests):
    candidates = discovery.get("candidates", [])
    admitted = {
        str(m.get("provenance", {}).get("source_subtree", "")).split("/")[-1]
        for m in manifests
    }
    selected = next(
        (c["package"] for c in candidates
         if c.get("package") not in admitted
         and c.get("package") not in {"path", "characters", "fixnum"}
         and c.get("state") == "DISCOVERED_UNTESTED"),
        None,
    )
    if selected is None:
        raise ValueError("no unadmitted external Dart package candidate")
    return {"schema": "aivexus.library.next-external-candidate.v1",
            "package": selected,
            "source_commit": discovery["source_commit"],
            "source_path": f"pkgs/{selected}",
            "status": "DISCOVERED_UNTESTED",
            "certification_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--intake", type=Path, default=Path("intake"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifests = [json.loads(p.read_text())
                 for p in sorted(args.intake.glob("**/manifest.json"))]
    result = select(json.loads(args.discovery.read_text()), manifests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
