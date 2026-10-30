"""Promote real Researcher-origin source to Linux-TESTED Library intake.

Never invokes untrusted code, uses exact GitHub PR CI receipts and verified
materialized SHA256. Security.reviewed remains false; no production deployment.
The protected workflow is the sole writer of this artifact.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from autonomous_public_dart_gate import inspect
from autonomous_public_dart_merger import REPO, REQUIRED, has_required_checks
from library_evidence import verify_test_evidence
from library_source_integrity import payload_tree_sha256

CONTRACTS = {
    "path": ("utility.path_operations", "utility.path_operations.v1",
             "Pure POSIX join and normalize; not actual filesystem access"),
    "characters": ("utility.text_graphemes", "utility.text_graphemes.v1",
                   "Pure Unicode grapheme counting"),
    "fixnum": ("utility.int64_arithmetic", "utility.int64_arithmetic.v1",
               "Pure fixed-width integer arithmetic"),
}


def github(path: str) -> dict | list:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("protected Library token required to verify real CI receipts")
    req = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(req, timeout=30) as handle:
        return json.loads(handle.read())


def source_proof(pkg: str) -> dict | None:
    prs = github("pulls?state=closed&base=main&per_page=100")
    if not isinstance(prs, list):
        raise ValueError("invalid GitHub merged PR response")
    qualified = []
    for pr in prs:
        if ((pr.get("head") or {}).get("ref") != "researcher/public-dart-" + pkg
                or (pr.get("head") or {}).get("repo", {}).get("full_name") != REPO
                or not pr.get("merged_at")
                or not pr.get("merge_commit_sha")):
            continue
        sha = (pr.get("head") or {}).get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            continue
        runs = github("actions/runs?head_sha=" + urllib.parse.quote(sha) + "&per_page=100")
        rows = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
        if not has_required_checks(rows, sha):
            continue
        proof = next((x for x in rows
                      if x.get("head_sha") == sha
                      and x.get("name") == "Library isolated verification of Researcher public Dart intake"
                      and x.get("event") == "pull_request"
                      and x.get("conclusion") == "success"), None)
        if proof is not None:
            qualified.append({"pr": pr, "ci": proof, "head": sha})
    if not qualified:
        return None
    return sorted(qualified, key=lambda x: x["pr"]["number"], reverse=True)[0]


def materialize(root: Path, pkg: str, receipt: dict) -> dict:
    assert pkg in CONTRACTS
    source_receipt = inspect(root, pkg)
    base = root / "sandbox/researcher_public_dart" / pkg
    upstream = json.loads((base / "metadata.json").read_text(encoding="utf-8"))
    cap, contract_id, scope = CONTRACTS[pkg]
    asset = cap + ".external.dartlang." + pkg
    version = "0.1.0"
    target = root / "intake" / asset / version
    if target.exists():
        return {"created": False, "reason": "already_recorded", "asset_id": asset}
    template = json.loads((root / "intake/diagnostics.logging.dartlang.logging_adapter/0.1.1/manifest.json").read_text())
    m = copy.deepcopy(template)
    m["id"] = asset
    m["name"] = "Dart " + pkg + " " + upstream["package_version"] + " — automatically imported Aivexus adapter"
    m["version"] = version
    m["status"] = "tested"
    m["description"] = scope + ". Public upstream source and Aivexus adapter were independently executed on Linux CI; not security-certified."
    m["tags"] = ["autonomous-researcher", "public-source", "dart", "source-materialized",
                 "tested-not-certified", "narrow-capability"]
    m["capabilities"] = [cap]
    m["platforms"] = ["linux"]
    m["frameworks"] = ["Dart"]
    m["languages"] = ["dart"]
    m["entry_paths"] = ["lib/aivexus_external.dart"]
    m["provenance"] = {
        "origin": "researcher",
        "source_repository": upstream["source_repository"],
        "source_commit": upstream["source_commit"],
        "source_tag": upstream["source_tag"],
        "source_subtree": upstream["source_subtree"],
        "source_project_id": None,
        "source_task_id": "researcher-autonomous-public-dart:" + pkg,
        "retrieved_at": receipt["ci"]["created_at"],
        "license": upstream["source_license"],
        "license_file": "provenance/LICENSE",
        "adapter_source": "Deterministic Aivexus adapter generated by Researcher from reviewed profile",
    }
    m["payload"] = {"type": "repository_path", "path": "payload/src",
                    "sha256": upstream["payload_sha256"],
                    "upstream_repository": upstream["source_repository"],
                    "upstream_commit": upstream["source_commit"]}
    m["validation"] = {
        "score": 0.8, "tests_passed": True,
        "test_report": "tests/dart-linux-ci-report.json",
        "validated_at": receipt["ci"]["updated_at"],
        "validated_on": ["linux"],
    }
    m["security"] = {
        "reviewed": False, "reviewed_at": None,
        "known_vulnerabilities": None, "sbom": None, "review_report": None,
        "notes": "No independent security/OSV/privacy/license clearance. Tested status is functional only.",
    }
    m["connector"] = {
        "standard": "ai-orchestrator-lego", "standard_version": "1.0.0",
        "integration_mode": "source_bundle",
        "provides": [{"capability_id": cap, "contract_id": contract_id,
                      "contract_version": "1.0"}],
        "requires": [], "adapters": [], "configuration_schema": None,
        "healthcheck": {"type": "none", "path": None},
    }
    m["integration"] = {
        "estimated_effort": "low", "adaptation_allowed": True,
        "adapter_notes": scope,
        "known_constraints": [
            "This narrow utility does not satisfy an entire broad platform need.",
            "Only Linux Dart execution has passed; no Android device proof.",
            "No independent license/security/privacy approval; not production installable.",
            "The upstream Git blobs are preserved exactly in payload/src/vendor.",
        ],
    }
    m["quality"] = {
        "reuse_count": 0, "successful_integrations": 0, "failed_integrations": 0,
        "last_used_at": None,
    }
    target.mkdir(parents=True, exist_ok=False)
    shutil.copytree(base / "payload/src", target / "payload/src", symlinks=False)
    (target / "provenance").mkdir()
    shutil.copyfile(base / ("payload/src/vendor/" + pkg + "/LICENSE"),
                    target / "provenance/LICENSE")
    if payload_tree_sha256(target / "payload/src") != source_receipt["payload_sha256"]:
        raise ValueError("source digest drift during Library promotion")
    test = {
        "schema": "ai-orchestrator.library-test-report.v1",
        "asset_id": asset, "version": version,
        "source_commit": upstream["source_commit"],
        "payload_sha256": upstream["payload_sha256"],
        "passed": True, "validated_on": ["linux"],
        "generated_at": receipt["ci"]["updated_at"],
        "evidence": {
            "github_run_id": receipt["ci"]["id"],
            "github_commit": receipt["head"],
            "researcher_merged_pr": receipt["pr"]["number"],
            "validated_workflows": sorted(REQUIRED),
            "checks": ["dart pub get --offline", "dart analyze lib",
                       "dart analyze tool", "dart run tool/self_test.dart"],
            "runtime": "Ubuntu Linux Dart SDK (read-only isolated PR runner)",
        },
        "independent_security_reviewed": False,
        "certification_authorized": False,
    }
    (target / "tests").mkdir()
    (target / "tests/dart-linux-ci-report.json").write_text(json.dumps(test, indent=2) + "\n")
    (target / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    verify_test_evidence(target, m)
    return {"created": True, "asset_id": asset, "path": str(target.relative_to(root)),
            "payload_sha256": upstream["payload_sha256"],
            "source_ci_run_id": receipt["ci"]["id"],
            "security_reviewed": False, "certification_authorized": False}


def run(root: Path) -> dict:
    for pkg in CONTRACTS:
        candidate = root / "sandbox/researcher_public_dart" / pkg / "metadata.json"
        if not candidate.is_file():
            continue
        asset = CONTRACTS[pkg][0] + ".external.dartlang." + pkg
        if (root / "intake" / asset / "0.1.0/manifest.json").exists():
            continue
        proof = source_proof(pkg)
        if proof is None:
            return {"created": False, "reason": "no_immutable_dual_ci_proof", "package": pkg}
        return materialize(root, pkg, proof)
    return {"created": False, "reason": "no_unadmitted_source"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
