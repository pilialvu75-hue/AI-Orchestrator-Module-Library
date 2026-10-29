"""Read-only independent review request for real, typed external Dart v0.1.1.

Never executes upstream Dart or signs any security decision. It verifies that
the previously blocking arbitrary event-string API was removed, but a static
source check is not a privacy audit or production authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from external_dart_logging_review import (
    ASSET, COMMIT, PIN, REPO, TREE, ExternalReviewError, checked_file,
    inventory, json_file, require, sha,
)
from library_evidence import EvidenceError, verify_test_evidence
from library_source_integrity import SourceIntegrityError, payload_tree_sha256

VERSION = "0.1.1"
CANDIDATE = Path("intake") / ASSET / VERSION
OLD = Path("intake") / ASSET / "0.1.0"
PAYLOAD = "2eaa1c85c6d116936bbfa461bd37173aa6ea6b3d841d58c2905ee421f39e0fab"
RUN_ID = 40929969173
RUN_SHA = "b9d42dc9994c9816e0eb0466aefaa21f69d52e69"
LOCAL = "pkg:generic/aivexus_external_logging@0.1.1"
ALLOWED_CODES = (
    "startupReady('startup_ready')",
    "localModelLoaded('local_model_loaded')",
    "retryScheduled('retry_scheduled')",
    "consumerStarted('consumer_started')",
    "moduleConnected('module_connected')",
)


def build_review_request(root: Path) -> dict:
    root = root.resolve()
    base = root / CANDIDATE
    original = root / OLD
    manifest_file = base / "manifest.json"
    manifest = json_file(manifest_file)
    prov = manifest.get("provenance") or {}
    payload = manifest.get("payload") or {}
    security = manifest.get("security") or {}
    validation = manifest.get("validation") or {}
    require(manifest.get("id") == ASSET and manifest.get("version") == VERSION
            and manifest.get("status") == "tested"
            and security.get("reviewed") is False,
            "typed candidate is not TESTED or has a forged security claim")
    require(prov.get("origin") == "open_source"
            and prov.get("source_repository") == REPO
            and prov.get("source_commit") == COMMIT
            and prov.get("source_git_tree") == TREE
            and prov.get("source_subtree") == "pkgs/logging"
            and prov.get("license") == "BSD-3-Clause"
            and prov.get("license_file") == "provenance/LICENSE",
            "upstream provenance or license pin differs")
    require(payload.get("type") == "repository_path"
            and payload.get("path") == "payload/src"
            and payload.get("sha256") == PAYLOAD
            and payload.get("upstream_commit") == COMMIT
            and payload.get("upstream_repository") == REPO,
            "typed adapter or source pin changed")
    require(validation.get("tests_passed") is True
            and validation.get("validated_on") == ["linux"]
            and manifest.get("platforms") == ["linux"],
            "unproven target or tests in typed module")
    source = base / "payload/src"
    try:
        digest = payload_tree_sha256(source)
        verify_test_evidence(base, manifest)
    except (SourceIntegrityError, EvidenceError, OSError) as exc:
        raise ExternalReviewError(f"typed source or test provenance invalid: {exc}") from exc
    require(digest == PAYLOAD, "typed payload content changed")

    receipt_path = base / "tests/dart-linux-ci-report.json"
    report = json_file(receipt_path)
    evidence = report.get("evidence") or {}
    require(report.get("schema") == "ai-orchestrator.library-test-report.v1"
            and report.get("asset_id") == ASSET
            and report.get("version") == VERSION
            and report.get("payload_sha256") == PAYLOAD
            and report.get("source_commit") == COMMIT
            and report.get("passed") is True
            and report.get("validated_on") == ["linux"]
            and report.get("independent_security_reviewed") is False
            and report.get("certification_authorized") is False
            and evidence.get("github_run_id") == RUN_ID
            and evidence.get("github_commit") == RUN_SHA
            and evidence.get("workflow_conclusion") == "success",
            "typed CI receipt changed or claims security review")

    source_files = inventory(source)
    old_root = original / "payload/src"
    old_files = inventory(old_root)
    require(len(source_files) == len(old_files) == 18,
            "original public Dart source inventory incomplete")
    old_upstream = old_root / "vendor/logging"
    new_upstream = source / "vendor/logging"
    old_upstream_files = {
        f["path"]: f["sha256"] for f in inventory(old_upstream)
    }
    new_upstream_files = {
        f["path"]: f["sha256"] for f in inventory(new_upstream)
    }
    require(len(new_upstream_files) == 13
            and new_upstream_files == old_upstream_files,
            "original public upstream source differs between versions")
    require(checked_file(source / "UPSTREAM_PROVENANCE.json")
            == checked_file(old_root / "UPSTREAM_PROVENANCE.json"),
            "pinned public Git blob inventory was modified")
    upstream = json_file(source / "UPSTREAM_PROVENANCE.json")
    require(upstream.get("source_git_tree_sha") == TREE
            and upstream.get("source_commit") == COMMIT
            and upstream.get("repository") == REPO
            and upstream.get("upstream_source_file_count") == 13,
            "upstream Git tree integrity metadata invalid")
    license_bytes = checked_file(source / "vendor/logging/LICENSE")
    require(license_bytes == checked_file(base / "provenance/LICENSE")
            and license_bytes == checked_file(original / "provenance/LICENSE"),
            "external source license differs or was removed")

    adapter = checked_file(source / "lib/aivexus_external_logging.dart").decode("utf-8")
    for code in ALLOWED_CODES:
        require(code in adapter, f"event vocabulary missing: {code}")
    require("enum AivexusEventCode {" in adapter
            and "void emit(AivexusEventCode code," in adapter
            and "_logger.log(level, code.wireCode);" in adapter
            and "Logger.detached(" in adapter
            and "void emit(String eventCode," not in adapter
            and "_code = RegExp" not in adapter
            and "dart:io" not in adapter,
            "closed-vocabulary Aivexus adapter privacy boundary changed")
    require("version: 0.1.1" in checked_file(source / "pubspec.yaml").decode("utf-8"),
            "typed adapter pubspec version incorrect")

    inventory_digest = {
        f["path"]: f["sha256"] for f in source_files
    }
    results = [
        {"finding": "FREE_FORM_EVENT_CODE_API", "state": "MITIGATED_IN_SOURCE_PENDING_INDEPENDENT_REVIEW",
         "observation": "v0.1.1 declares a finite event enum and emit accepts only that type; no arbitrary event strings are forwarded"},
        {"finding": "GLOBAL_LOGGER_AVAILABLE_IN_ORIGINAL_UPSTREAM", "state": "REQUIRES_REVIEW",
         "observation": "the upstream logging package supports global loggers; only the local Aivexus adapter uses detached logging"},
        {"finding": "HOST_PRIVACY_POLICY_AND_ANDROID_RUNTIME", "state": "REQUIRES_REVIEW",
         "observation": "separate Dart Linux consumer passed; production consent, retention, secure export, Android and Flutter host integration remain untested"},
    ]
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {"type": "application", "name": ASSET,
                                   "version": VERSION}},
        "components": [
            {"type": "library", "bom-ref": PIN, "name": "logging",
             "version": "1.3.0", "purl": PIN,
             "licenses": [{"license": {"id": "BSD-3-Clause"}}]},
            {"type": "library", "bom-ref": LOCAL, "name": "aivexus_external_logging",
             "version": VERSION,
             "properties": [{"name": "aivexus:payload-sha256", "value": PAYLOAD},
                            {"name": "aivexus:independently-reviewed", "value": "false"}]},
        ],
        "dependencies": [{"ref": LOCAL, "dependsOn": [PIN]},
                         {"ref": PIN, "dependsOn": []}],
    }
    return {
        "schema": "ai-orchestrator.external-logging-typed-review-request.v1",
        "status": "INDEPENDENT_REVIEW_REQUIRED",
        "candidate": f"{ASSET}@{VERSION}",
        "module_status": "tested",
        "source": {"repository": REPO, "commit": COMMIT,
                   "original_git_tree_sha": TREE, "combined_payload_sha256": PAYLOAD,
                   "manifest_sha256": sha(checked_file(manifest_file)),
                   "license_sha256": sha(license_bytes),
                   "file_hashes": inventory_digest, "file_count": 18},
        "functional_testing": {
            "test_claim_ci_run_id": RUN_ID, "test_claim_head_sha": RUN_SHA,
            "test_receipt_sha256": sha(checked_file(receipt_path)),
            "tested_host_claimed": ["linux"],
            "github_ci_conclusion_independently_rechecked_by_this_packet": False,
            "downstream_consumer": "PR #209 Linux CI (independent Dart package import)",
        },
        "dependency_inventory": {"cyclonedx_sbom": sbom, "dependencies": [PIN],
                                 "live_vulnerability_scan_completed": False},
        "findings": results,
        "independent_review_steps": [
            "Verify pin of full combined source tree, original public Git blobs, and BSD-3-Clause license",
            "Audit the closed event enum and ensure no bypass by direct import of upstream global logger",
            "Assess and test data minimization, local buffer lifecycle, PII risks and host transport/persistence",
            "Independently verify the signed/attested CI job and Linux integration proof; run fresh adversarial tests",
            "Perform dependency/advisory security checks and review original third-party attribution",
            "Authorize via independently controlled Ed25519 reviewer signature bound to source/SBOM/license only after review",
            "Test Flutter Android host integration separately before Android production distribution",
        ],
        "independent_security_reviewed": False,
        "license_approved_by_independent_reviewer": False,
        "reviewer_signature_present": False,
        "security_certified": False,
        "production_approved": False,
        "certification_authorized": False,
    }


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args.add_argument("--output", type=Path, required=True)
    params = args.parse_args()
    result = build_review_request(params.root)
    params.output.parent.mkdir(parents=True, exist_ok=True)
    params.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print("Real typed Dart external module evidence verified; independent approval required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
