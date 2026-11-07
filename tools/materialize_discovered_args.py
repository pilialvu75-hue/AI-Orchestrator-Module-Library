"""Materialize a tested-only Library candidate from actual upstream args source.

Must run AFTER upstream tests and independent consumer succeed in the same CI job.
Creates an artifact, not a certified asset or a silent main-branch commit.
"""
import copy
import hashlib
import json
import pathlib
import shutil
import sys
from datetime import datetime, timezone

def main():
    root = pathlib.Path(sys.argv[1])
    repo = pathlib.Path(sys.argv[2])
    discovery = json.loads((root / "discovered-modules.json").read_text())
    evidence = json.loads((root / "consumer-evidence.json").read_text())
    if discovery["selected_package"] != "args" or evidence["status"] != "CONSUMER_PASS":
        raise ValueError("verified args consumer receipt required")
    source = root / "upstream" / discovery["selected_source_path"]
    if not (source / "lib/args.dart").is_file():
        raise ValueError("upstream public args API missing")
    asset = "utility.cli_arguments.external.dartlang.args"
    dest = root / "library_candidate" / "intake" / asset / "0.1.0"
    payload = dest / "payload/src"
    payload.mkdir(parents=True)
    shutil.copytree(source, payload / "vendor/args", ignore=shutil.ignore_patterns(".dart_tool", "build", ".packages", "pubspec.lock"))
    shutil.copytree(source / "lib", payload / "lib/vendor/args")
    (payload / "lib/aivexus_external.dart").write_text(
        "export 'vendor/args/args.dart' show ArgParser, ArgResults, ArgParserException;\n")
    (payload / "pubspec.yaml").write_text(
        "name: aivexus_external_args\npublish_to: none\nenvironment:\n  sdk: ^3.4.0\n")
    # Keep the original source, its pinned revision, and the real CI evidence.
    from library_source_integrity import payload_tree_sha256
    digest = payload_tree_sha256(payload)
    template = json.loads((repo / "intake/utility.int64_arithmetic.external.dartlang.fixnum/0.1.0/manifest.json").read_text())
    manifest = copy.deepcopy(template)
    manifest.update(id=asset, name="Dart args — discovered and independently exercised",
                    description="CLI argument parsing; upstream and independent consumer tested on Linux; not certified.",
                    capabilities=["utility.cli_arguments"],
                    entry_paths=["lib/aivexus_external.dart"])
    manifest["connector"]["provides"] = [{
        "capability_id": "utility.cli_arguments",
        "contract_id": "utility.cli_arguments.v1",
        "contract_version": "1.0"}]
    manifest["provenance"].update(source_commit=discovery["source_commit"],
                                  source_subtree=discovery["selected_source_path"],
                                  source_tag=None,
                                  source_task_id="researcher-live-discovery:args",
                                  adapter_source="Deterministic re-export of actual upstream public API")
    manifest["payload"].update(sha256=digest, upstream_commit=discovery["source_commit"])
    manifest["validation"].update(test_report="tests/dart-linux-ci-report.json",
                                   validated_at=datetime.now(timezone.utc).isoformat())
    manifest["security"]["reviewed"] = False
    manifest["integration"]["adapter_notes"] = "Dart ArgParser public API re-export"
    (dest / "provenance").mkdir()
    shutil.copy2(source / "LICENSE", dest / "provenance/LICENSE")
    (dest / "tests").mkdir()
    receipt = {"schema":"ai-orchestrator.library-test-report.v1",
               "asset_id":asset,"version":"0.1.0","source_commit":discovery["source_commit"],
               "payload_sha256":digest,"passed":True,"validated_on":["linux"],
               "generated_at":manifest["validation"]["validated_at"],
               "evidence":{"github_run_id":__import__("os").environ.get("GITHUB_RUN_ID"),
                           "checks":["upstream dart test","independent consumer dart analyze",
                                     "independent consumer dart run bin/main.dart"]},
               "independent_security_reviewed":False,"certification_authorized":False}
    (dest / "tests/dart-linux-ci-report.json").write_text(json.dumps(receipt,indent=2)+"\n")
    (dest / "manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root / "library_candidate" / "README.txt").write_text(
        "TESTED-only candidate artifact; requires Library validation and controlled integration. NOT CERTIFIED.\n")
    print("Created tested-only candidate:",asset,"sha256:",digest)

if __name__ == "__main__":
    main()
