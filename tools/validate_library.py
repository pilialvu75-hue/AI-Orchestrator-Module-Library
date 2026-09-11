from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
VALID_STATUSES = {
    "discovered",
    "quarantined",
    "normalized",
    "tested",
    "certified",
    "deprecated",
    "revoked",
}
CATALOG_STATUSES = {"tested", "certified", "deprecated", "revoked"}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {exc}") from exc


def require(obj: dict, keys: list[str], path: Path) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise ValidationError(
            f"{path.relative_to(ROOT)}: missing required keys: {', '.join(missing)}"
        )


def validate_needs() -> None:
    path = ROOT / "catalog" / "needs.json"
    data = load_json(path)
    require(data, ["schema_version", "updated_at", "items"], path)
    if not isinstance(data["items"], list):
        raise ValidationError("catalog/needs.json: items must be an array")

    seen: set[str] = set()
    for item in data["items"]:
        if not isinstance(item, dict):
            raise ValidationError("catalog/needs.json: each item must be an object")
        require(
            item,
            [
                "capability_id",
                "title",
                "priority",
                "desired_candidates",
                "status",
                "targets",
            ],
            path,
        )
        capability_id = str(item["capability_id"]).strip()
        if not capability_id:
            raise ValidationError("catalog/needs.json: empty capability_id")
        if capability_id in seen:
            raise ValidationError(
                f"catalog/needs.json: duplicate capability_id {capability_id}"
            )
        seen.add(capability_id)
        if int(item["desired_candidates"]) < 1:
            raise ValidationError(
                f"catalog/needs.json: {capability_id} desired_candidates must be >= 1"
            )


def validate_connector(connector: dict, path: Path) -> None:
    require(
        connector,
        ["standard", "standard_version", "provides", "requires", "integration_mode"],
        path,
    )
    if connector["standard"] != "ai-orchestrator-lego":
        raise ValidationError(
            f"{path.relative_to(ROOT)}: connector.standard must be ai-orchestrator-lego"
        )
    provides = connector["provides"]
    if not isinstance(provides, list) or not provides:
        raise ValidationError(
            f"{path.relative_to(ROOT)}: connector.provides must not be empty"
        )
    for provided in provides:
        if not isinstance(provided, dict):
            raise ValidationError(
                f"{path.relative_to(ROOT)}: connector.provides entries must be objects"
            )
        if not provided.get("capability_id") or not provided.get("contract_id"):
            raise ValidationError(
                f"{path.relative_to(ROOT)}: every provided capability needs capability_id + contract_id"
            )


def validate_manifest(path: Path, *, under_modules: bool) -> tuple[str, str, str, list[str]]:
    data = load_json(path)
    require(
        data,
        [
            "id",
            "name",
            "version",
            "kind",
            "status",
            "description",
            "capabilities",
            "platforms",
            "provenance",
            "validation",
            "security",
            "integration",
            "connector",
            "payload",
        ],
        path,
    )

    asset_id = str(data["id"]).strip()
    version = str(data["version"]).strip()
    status = str(data["status"]).strip()
    capabilities = [str(value).strip() for value in data["capabilities"]]

    if not asset_id:
        raise ValidationError(f"{path.relative_to(ROOT)}: id cannot be empty")
    if not SEMVER.match(version):
        raise ValidationError(
            f"{path.relative_to(ROOT)}: invalid semantic version {version}"
        )
    if status not in VALID_STATUSES:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid status {status}")
    if not capabilities or any(not value for value in capabilities):
        raise ValidationError(
            f"{path.relative_to(ROOT)}: capabilities must contain non-empty values"
        )

    validate_connector(data["connector"], path)
    provided_capabilities = {
        str(value["capability_id"]).strip()
        for value in data["connector"]["provides"]
    }
    missing_connector = set(capabilities) - provided_capabilities
    if missing_connector:
        raise ValidationError(
            f"{path.relative_to(ROOT)}: capabilities missing from connector.provides: "
            + ", ".join(sorted(missing_connector))
        )

    if under_modules and status not in CATALOG_STATUSES:
        raise ValidationError(
            f"{path.relative_to(ROOT)}: modules/ may contain only tested/certified/deprecated/revoked assets"
        )

    if under_modules and status == "certified":
        validation = data["validation"]
        security = data["security"]
        if validation.get("tests_passed") is not True:
            raise ValidationError(
                f"{path.relative_to(ROOT)}: certified asset requires tests_passed=true"
            )
        if float(validation.get("score", 0)) < 0.8:
            raise ValidationError(
                f"{path.relative_to(ROOT)}: certified asset requires validation score >= 0.80"
            )
        if security.get("reviewed") is not True:
            raise ValidationError(
                f"{path.relative_to(ROOT)}: certified asset requires security.reviewed=true"
            )

    return asset_id, version, status, capabilities


def manifest_files(base: str) -> list[Path]:
    root = ROOT / base
    if not root.exists():
        return []
    return sorted(root.glob("**/manifest.json"))


def validate_catalog(module_manifests: dict[tuple[str, str], tuple[Path, str, list[str]]]) -> None:
    path = ROOT / "catalog" / "index.json"
    data = load_json(path)
    require(
        data,
        ["schema_version", "library_id", "catalog_version", "updated_at", "assets"],
        path,
    )
    if not SEMVER.match(str(data["catalog_version"])):
        raise ValidationError("catalog/index.json: catalog_version must be semantic")

    seen: set[tuple[str, str]] = set()
    for item in data["assets"]:
        require(item, ["id", "version", "manifest", "status", "capabilities"], path)
        key = (str(item["id"]), str(item["version"]))
        if key in seen:
            raise ValidationError(
                f"catalog/index.json: duplicate asset {key[0]}@{key[1]}"
            )
        seen.add(key)
        manifest_path = ROOT / str(item["manifest"])
        if not manifest_path.exists():
            raise ValidationError(
                f"catalog/index.json: missing manifest {item['manifest']}"
            )
        if key not in module_manifests:
            raise ValidationError(
                f"catalog/index.json: {key[0]}@{key[1]} is not stored under modules/"
            )
        _, manifest_status, manifest_capabilities = module_manifests[key]
        if item["status"] != manifest_status:
            raise ValidationError(
                f"catalog/index.json: status mismatch for {key[0]}@{key[1]}"
            )
        if set(item["capabilities"]) != set(manifest_capabilities):
            raise ValidationError(
                f"catalog/index.json: capability mismatch for {key[0]}@{key[1]}"
            )

    for key, (_, status, _) in module_manifests.items():
        if status in CATALOG_STATUSES and key not in seen:
            raise ValidationError(
                f"catalog/index.json: modules/{key[0]}@{key[1]} missing from catalog"
            )


def main() -> int:
    try:
        validate_needs()

        module_manifests: dict[tuple[str, str], tuple[Path, str, list[str]]] = {}
        for path in manifest_files("modules"):
            asset_id, version, status, capabilities = validate_manifest(
                path, under_modules=True
            )
            key = (asset_id, version)
            if key in module_manifests:
                raise ValidationError(
                    f"duplicate module manifest for {asset_id}@{version}"
                )
            module_manifests[key] = (path, status, capabilities)

        for path in manifest_files("intake"):
            validate_manifest(path, under_modules=False)

        validate_catalog(module_manifests)
    except ValidationError as exc:
        print(f"LIBRARY VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("LIBRARY VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
