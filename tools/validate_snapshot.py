from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"^[a-f0-9]{64}$")
AVAILABILITY = {"active", "deprecated", "revoked"}


class SnapshotError(Exception):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SnapshotError(f"invalid JSON: {exc}") from exc
    require(isinstance(value, dict), "snapshot must be a JSON object")
    return value


def validate(snapshot: dict) -> None:
    required = {
        "schema_version",
        "library_id",
        "catalog_version",
        "source_state",
        "resolution_policy",
        "contracts",
        "needs",
        "assets",
        "snapshot_sha256",
    }
    missing = sorted(required - snapshot.keys())
    require(not missing, "missing fields: " + ", ".join(missing))
    require(snapshot["schema_version"] == 1, "unsupported schema_version")
    require(isinstance(snapshot["library_id"], str) and snapshot["library_id"], "library_id is required")
    require(isinstance(snapshot["catalog_version"], str) and snapshot["catalog_version"], "catalog_version is required")
    require(isinstance(snapshot["contracts"], list), "contracts must be an array")
    require(isinstance(snapshot["needs"], list), "needs must be an array")
    require(isinstance(snapshot["assets"], list), "assets must be an array")

    declared_hash = snapshot["snapshot_sha256"]
    require(isinstance(declared_hash, str) and SHA256.fullmatch(declared_hash) is not None, "snapshot_sha256 is invalid")
    payload = dict(snapshot)
    payload.pop("snapshot_sha256", None)
    actual_hash = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    require(actual_hash == declared_hash, "snapshot_sha256 does not match snapshot content")

    seen: set[tuple[str, str]] = set()
    for asset in snapshot["assets"]:
        require(isinstance(asset, dict), "asset entries must be objects")
        asset_id = str(asset.get("id", ""))
        version = str(asset.get("version", ""))
        require(bool(asset_id and version), "asset id/version are required")
        key = (asset_id, version)
        require(key not in seen, f"duplicate asset {asset_id}@{version}")
        seen.add(key)
        require(asset.get("status") == "certified", f"snapshot asset is not certified: {asset_id}@{version}")
        require(asset.get("availability") in AVAILABILITY, f"invalid availability for {asset_id}@{version}")
        integrity = asset.get("integrity")
        require(isinstance(integrity, dict), f"missing integrity for {asset_id}@{version}")
        require(SHA256.fullmatch(str(integrity.get("manifest_sha256", ""))) is not None, f"invalid manifest hash for {asset_id}@{version}")
        require(SHA256.fullmatch(str(integrity.get("module_tree_sha256", ""))) is not None, f"invalid module tree hash for {asset_id}@{version}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python tools/validate_snapshot.py <snapshot.json>", file=sys.stderr)
        return 2
    try:
        validate(load(Path(args[0])))
    except SnapshotError as exc:
        print(f"LIBRARY SNAPSHOT VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    print("LIBRARY SNAPSHOT VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
