"""Review REQUEST only for autonomously imported, genuinely Linux-tested source.

Verifies the exact source and test evidence without executing upstream code,
without making a vulnerability-clean assertion and without signing anything.
The independent security reviewer owns final authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from autonomous_public_dart_admit import CONTRACTS
from autonomous_public_dart_gate import inspect
from library_evidence import verify_manifest_evidence
from library_source_integrity import payload_tree_sha256

REPO = "https://github.com/dart-lang/core"
SOURCE = "pkg:pub/"
SHA40 = re.compile(r"[a-f0-9]{40}$")
SHA256 = re.compile(r"[a-f0-9]{64}$")
IMPORT = re.compile(r"""(?:import|export)\s+['"]([^'"]+)['"]""")


def review(root: Path, pkg: str) -> dict:
    if pkg not in CONTRACTS:
        raise ValueError("unreviewed source profile")
    verified = inspect(root, pkg)
    capability = CONTRACTS[pkg][0]
    base = root / "intake" / (capability + ".external.dartlang." + pkg) / "0.1.0"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    provenance = manifest.get("provenance") or {}
    source = manifest.get("payload") or {}
    security = manifest.get("security") or {}
    check = manifest.get("validation") or {}
    if not (
        manifest.get("status") == "tested"
        and manifest.get("version") == "0.1.0"
        and manifest.get("capabilities") == [capability]
        and source.get("sha256") == verified["payload_sha256"]
        and provenance.get("source_repository") == REPO
        and provenance.get("source_commit") == verified["source_commit"]
        and provenance.get("source_tag") == verified["source_tag"]
        and provenance.get("license") == "BSD-3-Clause"
        and security.get("reviewed") is False
        and check.get("validated_on") == ["linux"]
        and check.get("tests_passed") is True
    ):
        raise ValueError("unapproved or source-mismatched tested candidate")
    verify_manifest_evidence(base, manifest)
    payload = base / "payload/src"
    if payload_tree_sha256(payload) != verified["payload_sha256"]:
        raise ValueError("real tested source changed")
    original = payload / "vendor" / pkg
    license_bytes = (original / "LICENSE").read_bytes()
    if license_bytes != (base / "provenance/LICENSE").read_bytes():
        raise ValueError("original license differs from recorded source")
    pubspec = (original / "pubspec.yaml").read_text(encoding="utf-8")
    if re.search(r"(?m)^dependencies:", pubspec):
        raise ValueError("additional upstream runtime dependency needs review")
    direct = (payload / "pubspec.yaml").read_text(encoding="utf-8")
    if ("path: vendor/" + pkg) not in direct or "git:" in direct:
        raise ValueError("unverified external adapter dependency")
    code = (payload / "lib/aivexus_external.dart").read_text(encoding="utf-8")
    expected_import = "package:" + pkg + "/" + pkg + ".dart"
    if sorted(set(IMPORT.findall(code))) != [expected_import]:
        raise ValueError("adapter imports changed; additional boundary review required")
    files: list[dict] = []
    for f in sorted(payload.rglob("*"), key=lambda p: p.as_posix()):
        if f.is_symlink():
            raise ValueError("symlink inside audited source")
        if f.is_file():
            content = f.read_bytes()
            files.append({"path": f.relative_to(payload).as_posix(),
                          "sha256": hashlib.sha256(content).hexdigest(),
                          "bytes": len(content)})
    if not files or len(files) > 512:
        raise ValueError("source file inventory exceeds bound")
    evidence = json.loads(
        (base / check["test_report"]).read_text(encoding="utf-8"))
    ci = evidence["evidence"]
    if (ci.get("github_run_id", 0) <= 0
            or not isinstance(ci.get("github_commit"), str)
            or not SHA40.fullmatch(ci["github_commit"])):
        raise ValueError("missing real CI identity")
    # Actual upstream package/version comes from the source-bound Researcher receipt.
    upstream = json.loads(
        (root / "sandbox/researcher_public_dart" / pkg / "metadata.json").read_text())
    version = upstream["package_version"]
    pkg_ref = SOURCE + pkg + "@" + version
    adapter_ref = "pkg:generic/aivexus_external_" + pkg + "@0.1.0"
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {
            "type": "library", "name": manifest["id"], "version": "0.1.0",
        }},
        "components": [
            {"type": "library", "bom-ref": pkg_ref, "purl": pkg_ref,
             "name": pkg, "version": version,
             "licenses": [{"license": {"id": "BSD-3-Clause"}}]},
            {"type": "library", "bom-ref": adapter_ref,
             "name": "aivexus_external_" + pkg, "version": "0.1.0",
             "properties": [
                 {"name": "aivexus:payload_sha256", "value": verified["payload_sha256"]},
                 {"name": "aivexus:independent_security_review", "value": "required"},
             ]},
        ],
        "dependencies": [{"ref": adapter_ref, "dependsOn": [pkg_ref]},
                         {"ref": pkg_ref, "dependsOn": []}],
    }
    return {
        "schema": "aivexus.library.autonomous-public-dart-review-request.v1",
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "asset_id": manifest["id"], "version": manifest["version"],
        "module_state": "tested",
        "source": {
            "repository": REPO,
            "commit": verified["source_commit"],
            "tag": verified["source_tag"],
            "payload_tree_sha256": verified["payload_sha256"],
            "manifest_sha256": hashlib.sha256(
                (base / "manifest.json").read_bytes()).hexdigest(),
            "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
            "original_upstream_files": verified["upstream_file_count"],
            "all_file_digests": files,
        },
        "tested_evidence": {
            "ci_run_id": ci["github_run_id"],
            "ci_head_sha": ci["github_commit"],
            "verified_on": ["linux"],
            "other_platforms_verified": [],
            "runtime_and_device_certified": False,
        },
        "dependency_inventory": {
            "cyclonedx_sbom": sbom,
            "upstream_runtime_dependencies": [],
            "adapter_imports": [expected_import],
            "live_advisory_or_vulnerability_scan_completed": False,
        },
        "independent_review_required_for": [
            "Original BSD-3-Clause copyright, authors and redistribution attribution",
            "Source license and downstream license compatibility",
            "Upstream and adapter code security/unsafe operations, trust boundaries",
            "Privacy: inputs, logged data, persistence, transport and lifetime",
            "Independent vulnerability/advisory scan and SBOM approval",
            "Protected Ed25519 review attestation bound to exact source, license and SBOM",
            "Flutter/Android and host-specific tests before app distribution",
        ],
        "reviewer_signature_present": False,
        "security_reviewed": False,
        "license_approved_by_independent_reviewer": False,
        "certification_authorized": False,
        "installed_in_ai_orchestrator": False,
    }


def collect(root: Path) -> dict:
    items = []
    for pkg, (capability, _, _) in CONTRACTS.items():
        path = root / "intake" / (capability + ".external.dartlang." + pkg) / "0.1.0/manifest.json"
        if path.is_file():
            items.append(review(root, pkg))
    return {"schema": "aivexus.library.autonomous-public-dart-review-collection.v1",
            "requests": items, "count": len(items),
            "independent_security_reviewed": False,
            "certification_authorized": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"requests": result["count"],
                      "certification_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
