#!/usr/bin/env python3
"""Generate a runnable, reusable Dart module from a constrained capability spec.

No model output is executed. Generated code and tests are deterministic.
"""
import argparse
import json
from pathlib import Path

SUPPORTED = "math.running_total.v1"


def generate(spec: dict, output: Path) -> None:
    if not isinstance(spec, dict) or spec.get("capability") != SUPPORTED:
        raise ValueError("unsupported module capability")
    if spec.get("language") != "dart":
        raise ValueError("only Dart is supported")
    if set(spec) != {"capability", "language"}:
        raise ValueError("unexpected specification fields")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    (output / "lib").mkdir()
    (output / "test").mkdir()
    (output / "pubspec.yaml").write_text(
        "name: aivexus_running_total\n"
        "description: Generated reusable integer running-total module\n"
        "version: 0.1.0\n"
        "environment:\n  sdk: '>=3.3.0 <4.0.0'\n"
        "dev_dependencies:\n  test: ^1.25.0\n",
        encoding="utf-8",
    )
    (output / "lib" / "aivexus_running_total.dart").write_text(
        "/// Reusable running total. Does not mutate the input.\n"
        "List<int> runningTotals(Iterable<int> values) {\n"
        "  var sum = 0;\n"
        "  return List<int>.unmodifiable(values.map((value) {\n"
        "    sum += value;\n"
        "    return sum;\n"
        "  }));\n"
        "}\n",
        encoding="utf-8",
    )
    (output / "test" / "aivexus_running_total_test.dart").write_text(
        "import 'package:test/test.dart';\n"
        "import 'package:aivexus_running_total/aivexus_running_total.dart';\n"
        "void main() {\n"
        "  test('empty input', () => expect(runningTotals([]), isEmpty));\n"
        "  test('positive and negative', () =>\n"
        "      expect(runningTotals([7, -2, 11]), [7, 5, 16]));\n"
        "  test('repeatable', () {\n"
        "    final input = [1, 2, 3];\n"
        "    expect(runningTotals(input), [1, 3, 6]);\n"
        "    expect(input, [1, 2, 3]);\n"
        "  });\n"
        "}\n",
        encoding="utf-8",
    )
    (output / "generation.json").write_text(
        json.dumps({"generator": "aivexus-module-v1", "spec": spec}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate(json.loads(args.spec.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
