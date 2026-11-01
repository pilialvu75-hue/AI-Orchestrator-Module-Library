"""Conservative independent Dart source audit; findings are not approvals."""
import json
import re
from pathlib import Path

RULES = {
    "PROCESS_EXECUTION": re.compile(r"\bProcess\s*\.\s*(?:run|start|runSync)\s*\("),
    "DYNAMIC_LIBRARY": re.compile(r"\bDynamicLibrary\s*\.\s*(?:open|process|executable)\s*\("),
    "NETWORK_CLIENT": re.compile(r"\b(?:HttpClient|Socket|WebSocket|RawSocket)\s*\("),
    "INSECURE_TLS": re.compile(r"badCertificateCallback\s*="),
    "SHELL_INVOCATION": re.compile(r"\b(?:bash|sh|powershell|cmd\.exe)\b"),
}
IMPORT = re.compile(r"""(?:import|export|part)\s+['"]([^'"]+)['"]""")


def audit(root: Path, request: dict) -> dict:
    asset = request["asset_id"]
    base = root / "intake" / asset / request["version"] / "payload" / "src"
    if not base.is_dir() or base.is_symlink():
        raise ValueError("materialized source missing")
    inventory = request["source"]["all_file_digests"]
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("source inventory missing")
    findings = []
    import hashlib
    for entry in inventory:
        name = entry["path"]
        if not isinstance(name, str) or name.startswith("/") or "\\" in name or any(p in ("", ".", "..") for p in name.split("/")):
            raise ValueError("unsafe source path")
        path = base / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("source inventory file missing or symlink")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"] or len(raw) != entry["bytes"]:
            raise ValueError("source inventory digest mismatch")
        if not name.endswith(".dart"):
            continue
        source = raw.decode("utf-8")
        for key, pattern in RULES.items():
            for match in pattern.finditer(source):
                findings.append({"file": name, "rule": key, "offset": match.start()})
        for match in IMPORT.finditer(source):
            uri = match.group(1)
            if uri.startswith(("dart:io", "dart:ffi", "dart:mirrors")):
                findings.append({"file": name, "rule": "SENSITIVE_IMPORT", "import": uri})
    return {"asset_id": asset, "source_payload_sha256": request["source"]["payload_tree_sha256"],
            "findings": findings, "static_scan_completed": True,
            "manual_security_review_required": True, "security_reviewed": False,
            "certification_authorized": False}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests = json.loads(args.requests.read_text())
    result = {"schema": "aivexus.library.static-source-audit.v1",
              "items": [audit(args.root, item) for item in requests["requests"]],
              "security_reviewed": False, "certification_authorized": False}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
