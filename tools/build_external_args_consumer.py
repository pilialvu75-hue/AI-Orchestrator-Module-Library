"""Build a separate runnable Dart consumer for the automatically discovered args package.

The consumer is outside the vendored upstream tree and imports its real public API.
"""
import json
import pathlib
import sys

def main():
    discovery = json.loads(pathlib.Path(sys.argv[1]).read_text())
    root = pathlib.Path(sys.argv[2])
    package = discovery["selected_package"]
    if package != "args":
        raise ValueError("No independent consumer contract for discovered package: " + package)
    upstream = root / "upstream" / discovery["selected_source_path"]
    assert (upstream / "pubspec.yaml").is_file()
    consumer = root / "independent_consumer"
    (consumer / "bin").mkdir(parents=True, exist_ok=True)
    (consumer / "pubspec.yaml").write_text(
        "name: aivexus_independent_args_consumer\n"
        "publish_to: none\n"
        "environment:\n  sdk: ^3.4.0\n"
        "dependencies:\n  args:\n    path: " + str(upstream) + "\n"
    )
    (consumer / "bin" / "main.dart").write_text("""import 'package:args/args.dart';

void main() {
  final parser = ArgParser()
    ..addOption('name', defaultsTo: 'world')
    ..addFlag('verbose', negatable: true);
  final results = parser.parse(['--name', 'AIVEXUS', '--verbose', 'input.txt']);
  if (results['name'] != 'AIVEXUS') throw StateError('option failed');
  if (results['verbose'] != true) throw StateError('flag failed');
  if (results.rest.single != 'input.txt') throw StateError('positional failed');
  final defaults = parser.parse([]);
  if (defaults['name'] != 'world' || defaults['verbose'] != false) {
    throw StateError('defaults failed');
  }
  var rejected = false;
  try {
    parser.parse(['--unknown-option']);
  } on FormatException {
    rejected = true;
  }
  if (!rejected) throw StateError('invalid option not rejected');
  print('PASS: independent AIVEXUS consumer used actual upstream args API (5 assertions)');
}
""")
    (root / "consumer-evidence.json").write_text(json.dumps({
        "package": package, "source_commit": discovery["source_commit"],
        "consumer": "independent_consumer/bin/main.dart",
        "checks": ["option", "flag", "positional", "defaults", "invalid option"],
        "status": "GENERATED_NOT_YET_EXECUTED", "certified": False,
    }, indent=2) + "\n")
    print("Generated separate consumer for", package)

if __name__ == "__main__":
    main()
