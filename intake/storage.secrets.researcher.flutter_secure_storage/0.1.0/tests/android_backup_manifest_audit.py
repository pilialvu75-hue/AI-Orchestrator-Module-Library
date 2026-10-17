"""Read-only Android APK merged-manifest backup policy triage.

Consumes *text* from 'aapt2 dump xmltree APK AndroidManifest.xml'.
This cannot certify backup/restore safety: effective resource XML and runtime
device-to-device transfer behavior require independent inspection and testing.
No APK installation, secret access, network requests or source execution.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

APP = re.compile(r"^(?P<indent>\s*)E:\s+application(?:\s|$)", re.MULTILINE)
ATTR = re.compile(
    r"^\s*A:\s+android:(?P<name>allowBackup|dataExtractionRules|fullBackupContent)"
    r"\([^)]*\)=(?P<value>.+)$"
)


def _attribute_values(xmltree: str) -> dict[str, str]:
    values: dict[str, str] = {}
    inside = False
    app_indent = 0
    for line in xmltree.splitlines():
        app = APP.match(line)
        if app is not None:
            inside = True
            app_indent = len(app.group("indent"))
            continue
        if not inside:
            continue
        level = len(line) - len(line.lstrip())
        # aapt2 prints direct app attributes before its nested E: children.
        # Never confuse an activity/service attribute with app-level policy.
        if line.lstrip().startswith("E:"):
            break
        # Only immediate app attributes are trusted; nested attrs cannot count.
        if level <= app_indent or line.lstrip().startswith("E:"):
            continue
        match = ATTR.match(line)
        if match:
            values[match.group("name")] = match.group("value").strip()
    return values


def _bool_value(raw: str | None) -> str:
    if raw is None:
        return "NOT_DECLARED"
    normalized = raw.casefold().replace(" ", "")
    if normalized in {"false", "0", "(type0x12)0x0", "(type0x12)0x00000000"}:
        return "EXPLICIT_FALSE"
    if normalized in {"true", "1", "(type0x12)0xffffffff", "(type0x12)0x1"}:
        return "EXPLICIT_TRUE"
    return "UNKNOWN_VALUE"


def audit(xmltree: str) -> dict[str, Any]:
    if not APP.search(xmltree):
        raise ValueError("no application element in aapt2 xmltree output")
    values = _attribute_values(xmltree)
    backup = _bool_value(values.get("allowBackup"))
    extraction = "REFERENCED" if values.get("dataExtractionRules") else "NOT_DECLARED"
    full = "REFERENCED" if values.get("fullBackupContent") else "NOT_DECLARED"
    reasons: list[str] = []
    if backup != "EXPLICIT_FALSE":
        reasons.append("BACKUP_NOT_EXPLICITLY_DISABLED")
    if extraction != "REFERENCED":
        reasons.append("ANDROID12_EXTRACTION_POLICY_UNRESOLVED")
    if full != "REFERENCED":
        reasons.append("LEGACY_BACKUP_POLICY_UNRESOLVED")

    # Even explicit false and rule refs are NOT evidence of correct policy:
    # aapt2 manifest xmltree does not show referenced XML resource contents.
    return {
        "schema": "ai-orchestrator.android-secrets-apk-manifest-triage.v1",
        "state": "EVIDENCE_INCOMPLETE",
        "merged_manifest_observed": True,
        "apk_identity_verified": False,
        "allow_backup": backup,
        "data_extraction_rules": extraction,
        "full_backup_content": full,
        "reasons": reasons,
        "cloud_transfer_effective_policy_verified": False,
        "device_transfer_effective_policy_verified": False,
        "keystore_restore_fixture_tested": False,
        "library_certified": False,
        "app_change_authorized": False,
        "secret_material_examined": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aapt2-xmltree", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.aapt2_xmltree.read_text(encoding="utf-8"))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
