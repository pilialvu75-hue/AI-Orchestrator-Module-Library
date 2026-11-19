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
    if not isinstance(trials, list) or not (1 <= len(trials) <= 32):
        raise ValueError("expected 1 to 32 independent module specifications")
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
    use_local = os.environ.get("MODULE_LLM_LOCAL") == "ollama"
    endpoint = os.environ.get("MODULE_LLM_ENDPOINT", "")
    model = os.environ.get("MODULE_LLM_MODEL", "")
    token = os.environ.get("MODULE_LLM_API_KEY", "")
    if use_local:
        # The model is actually executed inside an isolated GitHub runner,
        # without credentials, paid inference or any pretrained source fixtures.
        from generate_local_ollama_candidate import generate_local
        model = "qwen2.5-coder:3b"
    elif not token or not model or not endpoint.startswith("https://"):
        raise RuntimeError("BLOCKED: configure real HTTPS LLM endpoint/model and a zero-cost-approved API credential")
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("generation output must start empty")
    output.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        folder = output / spec["id"]
        # Every module goes through the SAME generator, no prewritten Dart
        # source, no canned response, and never a fallback to running_total.
        if use_local:
            generate_local(
                spec["instruction"], folder, model=model,
                package_name=spec["package_name"],
                library_path=spec["library_path"],
                acceptance_source=spec["consumer_source"],
            )
        else:
            generate(spec["instruction"], folder, endpoint=endpoint, model=model, api_key=token)
        check_source(folder, spec)
        print(f"LLM_SOURCE_GENERATED {spec['id']} provider_model={model}", flush=True)


def _split_params(raw):
    # Split typed Dart parameters without splitting inside List<(int,int)>.
    result, part, depth = [], "", 0
    for char in raw:
        if char in "<([{":
            depth += 1
        elif char in ">)]}":
            depth -= 1
        if char == "," and depth == 0:
            result.append(part.strip())
            part = ""
        else:
            part += char
    if part.strip():
        result.append(part.strip())
    return result


def _adapt_static_class_api(spec, folder):
    """Add no-logic top-level wrappers for model-generated static methods.

    This generic contract adapter delegates to the *model's* actual
    implementation. It cannot fabricate a function body or replace failed
    behavioral logic; real Dart/analyzer and independent consumer still gate.
    """
    path = folder / spec["library_path"]
    source = path.read_text(encoding="utf-8")
    klass = re.search(r"(?m)^\s*class\s+([A-Za-z_]\w*)\s*\{", source)
    if klass is None:
        return
    wrappers = []
    for match in re.finditer(
            r"(?m)^\s*static\s+([^\n]+?)\s+([a-z]\w*)\s*\(([^\n]*)\)\s*\{",
            source):
        return_type, name, params = (m.strip() for m in match.groups())
        if not re.search(r"\b" + re.escape(name) + r"\s*\(",
                         spec["consumer_source"]):
            continue
        if re.search(r"(?m)^" + re.escape(return_type) + r"\s+" +
                     re.escape(name) + r"\s*\(", source):
            continue
        parameters = _split_params(params)
        arg_names = []
        for param in parameters:
            m = re.search(r"\b([A-Za-z_]\w*)\s*$", param)
            if m is None or "=" in param or "{" in param or "[" in param:
                arg_names = []
                break
            arg_names.append(m.group(1))
        if len(arg_names) != len(parameters):
            continue
        wrappers.append(
            f"{return_type} {name}({params}) => "
            f"{klass.group(1)}.{name}({', '.join(arg_names)});"
        )
    if not wrappers:
        return
    path.write_text(source.rstrip() + "\n\n" +
                    "\n".join(wrappers) + "\n", encoding="utf-8")
    meta = folder / "generation.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["adaptation"] = "generic-static-api-forwarders-only"
    data["adapter_forwarders"] = len(wrappers)
    meta.write_text(json.dumps(data, sort_keys=True) + "\n",
                    encoding="utf-8")


def _repair_missing_dart_math_import(spec, output, diagnostic):
    """Fix only a real Dart analyzer missing max/min import; never invent logic.

    This is compiler-driven source packaging, not functional implementation.
    The actual Dart tests and a separate consumer MUST pass after adaptation.
    """
    names = []
    for symbol in ("max", "min"):
        if (f"The method '{symbol}' isn't defined" in diagnostic or
                f"Undefined name '{symbol}'" in diagnostic):
            names.append(symbol)
    if not names:
        return False
    path = output / spec["id"] / spec["library_path"]
    if not path.is_file() or path.is_symlink():
        return False
    source = path.read_text(encoding="utf-8")
    if "import 'dart:math'" in source or 'import "dart:math"' in source:
        # Do not attempt to repair namespace/shadowing mistakes blindly.
        return False
    needed = [name for name in names
              if re.search(r"(?<![.\w])" + name + r"\s*\(", source)]
    if not needed:
        return False
    path.write_text("import 'dart:math' show " + ", ".join(needed) +
                    ";\n" + source, encoding="utf-8")
    meta = path.parents[1] / "generation.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    fixes = data.get("compiler_driven_repairs", [])
    if not isinstance(fixes, list):
        fixes = []
    fixes.append({
        "kind": "dart_math_missing_import_only",
        "symbols": needed,
        "diagnostic_sha256": hashlib.sha256(
            diagnostic.encode("utf-8")).hexdigest(),
    })
    data["compiler_driven_repairs"] = fixes
    meta.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    return True


def _verify_one(spec, output):
    folder = output / spec["id"]
    metadata = check_source(folder, spec)
    _adapt_static_class_api(spec, folder)
    # Don't run arbitrary model-authored Dart IO/process/network tests.
    # The generated package is still UNTRUSTED, isolated on a throwaway
    # runner without secrets or write privileges; this is an additional
    # admission-time check, not a security certification.
    for target in list((folder / "lib").glob("*.dart")) + list(
            (folder / "test").glob("*_test.dart")):
        source = target.read_text(encoding="utf-8")
        for imported in re.findall(
                r"""(?:import|export|part)\s+['"]([^'"]+)['"]""", source):
            if imported.startswith("dart:") and imported not in {
                    "dart:core", "dart:math", "dart:collection", "dart:convert"}:
                raise ValueError(f"forbidden Dart SDK import {imported}")
            if imported.startswith("package:"):
                allowed = imported.startswith(
                    "package:" + spec["package_name"] + "/")
                is_test = (target.parent.name == "test"
                           and imported == "package:test/test.dart")
                if not (allowed or is_test):
                    raise ValueError(f"forbidden third-party import {imported}")
    run(["dart", "pub", "get"], folder)
    run(["dart", "format", "lib", "test"], folder)
    run(["dart", "analyze", "--fatal-infos"], folder)
    run(["dart", "test"], folder)

    # A separate application is written by the independent acceptance
    # contract, never by the model. Recreate it on each repair attempt.
    consumer = output / "_consumers" / spec["id"]
    if consumer.exists():
        import shutil
        shutil.rmtree(consumer)
    consumer.joinpath("bin").mkdir(parents=True, exist_ok=False)
    consumer.joinpath("pubspec.yaml").write_text(
        "name: p0_independent_" + spec["id"] + "\n"
        "publish_to: none\n"
        "environment:\n  sdk: '>=3.3.0 <4.0.0'\n"
        "dependencies:\n  " + spec["package_name"] + ":\n    path: " +
        str(folder.resolve()) + "\n", encoding="utf-8"
    )
    consumer.joinpath("bin", "main.dart").write_text(
        spec["consumer_source"], encoding="utf-8"
    )
    run(["dart", "pub", "get"], consumer)
    run(["dart", "analyze", "--fatal-infos"], consumer)
    run(["dart", "run", "bin/main.dart"], consumer)
    source = folder / spec["library_path"]
    return {
        "id": spec["id"], "package": spec["package_name"],
        "model": metadata["model"],
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "dart_tests": "PASS", "separate_consumer": "PASS",
        "repairs": int(metadata.get("attempt", 0)),
        "status": "TESTED_IN_ISOLATION_NOT_ADMITTED",
    }


def verify_packages(specs, output, report_path):
    report = {"schema": "aivexus.p0-llm-module-consumer.v1",
              "certified": False, "production_approved": False,
              "complete": False, "has_usable_module": False,
              "modules": []}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    use_local = os.environ.get("MODULE_LLM_LOCAL") == "ollama"
    try:
        for spec in specs:
            failure = ""
            result = None
            # Exactly 1 initial attempt + at most 2 model-authored repairs.
            for attempt in range(3):
                try:
                    result = _verify_one(spec, output)
                    break
                except (ValueError, RuntimeError, OSError,
                        subprocess.TimeoutExpired) as exc:
                    failure = str(exc)[-_MAX_CAPTURE:]
                    print(f"MODULE_TEST_BLOCKED {spec['id']} attempt={attempt} "
                          f"diagnostic={failure[-800:]}", flush=True)
                    # A missing permitted SDK import is a packaging error, not
                    # an algorithmic failure: apply a minimal compiler-driven
                    # repair before spending another Qwen generation attempt.
                    if use_local and _repair_missing_dart_math_import(
                            spec, output, failure):
                        try:
                            result = _verify_one(spec, output)
                            break
                        except (ValueError, RuntimeError, OSError,
                                subprocess.TimeoutExpired) as adapted_error:
                            failure = str(adapted_error)[-_MAX_CAPTURE:]
                            print(f"MODULE_SDK_IMPORT_REPAIR_BLOCKED {spec['id']} "
                                  f"diagnostic={failure[-800:]}", flush=True)
                    if attempt >= 2 or not use_local:
                        break
                    from generate_local_ollama_candidate import generate_local
                    try:
                        generate_local(
                            spec["instruction"], output / spec["id"],
                            model="qwen2.5-coder:3b", feedback=failure,
                            package_name=spec["package_name"],
                            library_path=spec["library_path"],
                            acceptance_source=spec["consumer_source"],
                        )
                    except (ValueError, RuntimeError, OSError) as repair_error:
                        failure = ("LLM repair failed: " +
                                   str(repair_error)[-_MAX_CAPTURE:])
                        break
            if result is None:
                report["modules"].append({
                    "id": spec["id"], "package": spec["package_name"],
                    "dart_tests": "BLOCKED", "separate_consumer": "BLOCKED",
                    "reason": failure[-1000:],
                    "status": "UNVALIDATED",
                })
            else:
                report["modules"].append(result)
        report["complete"] = (
            len(report["modules"]) == len(specs)
            and all(m["status"] == "TESTED_IN_ISOLATION_NOT_ADMITTED"
                    for m in report["modules"])
        )
        report["has_usable_module"] = any(
            m["status"] == "TESTED_IN_ISOLATION_NOT_ADMITTED"
            for m in report["modules"]
        )
    finally:
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if not report["has_usable_module"]:
        raise RuntimeError("P0 BLOCKED: no real module passed the independent consumer")
    print("P0: at least one real module passed; others remain BLOCKED if incomplete")
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
