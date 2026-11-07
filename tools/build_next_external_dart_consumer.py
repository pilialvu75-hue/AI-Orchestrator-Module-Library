"""Build an independent consumer for a selected upstream Dart package.

The consumer imports the actual public library, never the upstream test suite.
A successful run proves dependency resolution and public API import, not functional
certification or independent behavior coverage.
"""
import argparse
import json
from pathlib import Path
import re

SAFE = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def build(candidate, upstream_root, output):
    package = candidate["package"]
    if not SAFE.fullmatch(package):
        raise ValueError("unsafe package name")
    source = upstream_root / candidate["source_path"]
    if not source.is_dir() or not (source / "pubspec.yaml").is_file():
        raise ValueError("missing pinned upstream package")
    libraries = sorted((source / "lib").glob("*.dart"))
    preferred = source / "lib" / f"{package}.dart"
    library = preferred if preferred.is_file() else next(
        (p for p in libraries if not p.name.endswith(("_test.dart", ".g.dart"))), None
    )
    if library is None:
        raise ValueError("no public Dart entrypoint for independent consumer")
    output.mkdir(parents=True, exist_ok=True)
    (output / "bin").mkdir(exist_ok=True)
    (output / "pubspec.yaml").write_text(
        f"name: aivexus_next_package_consumer\npublish_to: none\n"
        f"environment:\n  sdk: ^3.4.0\ndependencies:\n"
        f"  {package}:\n    path: {source.resolve()}\n"
    )
    if package == "async" and library.name == "async.dart":
        consumer_source = """import 'dart:async';
import 'package:async/async.dart';

Future<void> main() async {
  final queue = StreamQueue<int>(Stream<int>.fromIterable([3, 5, 8]));
  if (await queue.next != 3) throw StateError('first item incorrect');
  if (await queue.peek != 5) throw StateError('peek incorrect');
  if (await queue.next != 5) throw StateError('peek consumed an item');
  if (await queue.next != 8) throw StateError('last item incorrect');
  if (await queue.hasNext) throw StateError('stream should be exhausted');
  await queue.cancel();
  print('PASS: independent async StreamQueue behavior (5 assertions)');
}
"""
        consumer_kind = "async_streamqueue_behavior"
        behavior_tested = True
    else:
        consumer_source = (
            f"// ignore: unused_import\\nimport 'package:{package}/{library.name}';\\n"
            "void main() { print('PASS: independent public API import'); }\\n"
        )
        consumer_kind = "import_smoke_only"
        behavior_tested = False
    (output / "bin" / "main.dart").write_text(consumer_source)
    return {"package": package, "source_commit": candidate["source_commit"],
            "public_library": library.name,
            "consumer_kind": consumer_kind,
            "behavior_tested": behavior_tested,
            "admission_authorized": False, "certification_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = build(json.loads(args.candidate.read_text()), args.upstream, args.output)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
