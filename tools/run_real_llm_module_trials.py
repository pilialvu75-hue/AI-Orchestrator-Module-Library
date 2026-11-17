#!/usr/bin/env python3
"""Real LLM -> two distinct Dart packages -> isolated independent consumers.

Generation uses the existing OpenAI-compatible client. The verification mode
never receives provider credentials and runs in a different read-only CI job.
No source templates, certification, GitHub writes or production installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from generate_llm_dart_candidate import generate

TRIAL_SCHEMA = "aivexus.module-llm-trials.v1"
_MAX_CAPTURE = 2500


def read_trials(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != TRIAL_SCHEMA:
        raise ValueError("invalid module trial specification")
    trials = data.get("trials")
    if not isinstance(trials, list) or len(trials) != 2:
        raise ValueError("P0 requires exactly two distinct module specifications")
    ids = set()
    for trial in trials:
        if not isinstance(trial, dict) or set(trial) != {
            "id", "package_name", "library_path", "instruction", "consumer_source"
        }:
            raise ValueError("invalid independent module contract")
        name = trial["id"]
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_]{1,48}", name) is None or name in ids:
            raise ValueError("duplicate or unsafe module id")
        ids.add(name)
        package = trial["package_name"]
        library = trial["library_path"]
        if (not isinstance(package, str) or re.fullmatch(r"[a-z][a-z0-9_]{1,60}", package) is None
                or not isinstance(library, str) or
                re.fullmatch(r"lib/[a-z][a-z0-9_]*[.]dart", library) is None):
            raise ValueError("invalid Dart package contract")
        for key in ("instruction", "consumer_source"):
            if not isinstance(trial[key], str) or not trial[key].strip() or len(trial[key]) > 10000:
                raise ValueError("empty or oversized trial input")
    return trials


def run(command, folder):
    result = subprocess.run(
        command, cwd=folder, capture_output=True, text=True,
        timeout=180, check=False, env={**os.environ, "CI": "true"},
    )
    if result.returncode:
        detail = (result.stderr + "\n" + result.stdout)[-_MAX_CAPTURE:]
        raise RuntimeError(f"{' '.join(command)} failed (exit {result.returncode}): {detail}")
    return result


def check_source(package_dir, spec):
    # Model-authored pubspec and lib MUST implement an independently authored
    # public contract; the model's own tests alone never prove functionality.
    pubspec = (package_dir / "pubspec.yaml").read_text(encoding="utf-8")
    name = re.search(r"(?m)^name:[ ]*([a-z][a-z0-9_]*)[ ]*$", pubspec)
    if name is None or name.group(1) != spec["package_name"]:
        raise ValueError("model package name does not match independent contract")
    if not (package_dir / spec["library_path"]).is_file():
        raise ValueError("model did not implement required library entrypoint")
    if not any((package_dir / "test").glob("*_test.dart")):
        raise ValueError("model omitted behavioral Dart tests")
    metadata = json.loads((package_dir / "generation.json").read_text())
    if (metadata.get("generator") != "aivexus-llm-candidate-v1"
            or metadata.get("status") != "UNVALIDATED"
            or not metadata.get("model")):
        raise ValueError("missing actual LLM generation provenance")
    return metadata


def generate_packages(specs, output):
    endpoint = os.environ.get("MODULE_LLM_ENDPOINT", "")
    model = os.environ.get("MODULE_LLM_MODEL", "")
    token = os.environ.get("MODULE_LLM_API_KEY", "")
    if not token or not model or not endpoint.startswith("https://"):
        raise RuntimeError("BLOCKED: configure real HTTPS LLM endpoint/model and a zero-cost-approved API credential")
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("generation output must start empty")
    output.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        folder = output / spec["id"]
        # Every module goes through the SAME generator, no prewritten Dart
        # source, no canned response, and never a fallback to running_total.
        generate(spec["instruction"], folder, endpoint=endpoint, model=model, api_key=token)
        check_source(folder, spec)
        print(f"LLM_SOURCE_GENERATED {spec['id']} provider_model={model}", flush=True)


def verify_packages(specs, output, report_path):
    report = {"schema": "aivexus.p0-llm-module-consumer.v1",
              "certified": False, "production_approved": False,
              "complete": False, "modules": []}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        for spec in specs:
            folder = output / spec["id"]
            metadata = check_source(folder, spec)
            run(["dart", "pub", "get"], folder)
            run(["dart", "format", "lib", "test"], folder)
            run(["dart", "analyze", "--fatal-infos"], folder)
            run(["dart", "test"], folder)

            # A separate real application with independent acceptance source
            # imports the package by path rather than executing a copied test
            # from the model-generated package.
            consumer = output / "_consumers" / spec["id"]
            consumer.joinpath("bin").mkdir(parents=True, exist_ok=False)
            consumer.joinpath("pubspec.yaml").write_text(
                "name: p0_independent_" + spec["id"] + "\n"
                "publish_to: none\n"
                "environment:\n  sdk: '>=3.3.0 <4.0.0'\n"
                "dependencies:\n  " + spec["package_name"] + ":\n    path: " +
                str(folder.resolve()) + "\n",
                encoding="utf-8",
            )
            consumer.joinpath("bin", "main.dart").write_text(
                spec["consumer_source"], encoding="utf-8"
            )
            run(["dart", "pub", "get"], consumer)
            run(["dart", "analyze", "--fatal-infos"], consumer)
            run(["dart", "run", "bin/main.dart"], consumer)
            source = folder / spec["library_path"]
            report["modules"].append({
                "id": spec["id"], "package": spec["package_name"],
                "model": metadata["model"], "source_sha256":
                hashlib.sha256(source.read_bytes()).hexdigest(),
                "dart_tests": "PASS", "separate_consumer": "PASS",
                "status": "TESTED_IN_ISOLATION_NOT_ADMITTED",
            })
        report["complete"] = len(report["modules"]) == len(specs)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        report["blocked_reason"] = str(exc)[-1000:]
        raise
    finally:
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.generate == args.verify:
        parser.error("select exactly one of --generate or --verify")
    trials = read_trials(args.spec)
    if args.generate:
        generate_packages(trials, args.output)
    else:
        if args.report is None:
            parser.error("--report required for --verify")
        verify_packages(trials, args.output, args.report)


if __name__ == "__main__":
    main()
