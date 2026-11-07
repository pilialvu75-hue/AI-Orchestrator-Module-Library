"""Build an isolated AIVEXUS Dart adapter for a tested upstream async package.

Creates a CI artifact, not an admitted or certified Library module.
"""
import argparse
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    if candidate["package"] != "async":
        raise ValueError("no verified packaged adapter contract for selected package")
    source = args.upstream / candidate["source_path"]
    if not (source / "lib/async.dart").is_file():
        raise ValueError("upstream async API missing")
    adapter = args.output
    vendor = adapter / "vendor/async"
    shutil.copytree(source, vendor, ignore=shutil.ignore_patterns(
        ".dart_tool", "build", ".packages", "pubspec.lock"))
    (adapter / "lib").mkdir(parents=True)
    (adapter / "lib/aivexus_external.dart").write_text(
        "export 'package:async/async.dart' show StreamQueue;\n"
    )
    (adapter / "pubspec.yaml").write_text(
        "name: aivexus_external_async\npublish_to: none\n"
        "environment:\n  sdk: ^3.4.0\ndependencies:\n"
        "  async:\n    path: vendor/async\n"
    )
    receipt = {"schema": "aivexus.library.adapter-build.v1",
               "package": "async", "source_commit": candidate["source_commit"],
               "adapter_path": str(adapter), "status": "BUILT_NOT_TESTED",
               "admission_authorized": False, "certification_authorized": False}
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
