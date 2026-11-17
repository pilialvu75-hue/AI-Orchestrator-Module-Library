#!/usr/bin/env python3
"""Generate and at most twice repair real open-weight model Dart source.

Every revision comes from Ollama; no hard-coded Dart files, manual patches,
external API keys or fallback generators. Preserve source revision receipts.
"""
import hashlib
import json
from pathlib import Path
import urllib.request

from generate_llm_dart_candidate import validate_files

ENDPOINT = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5-coder:3b"


def _sha(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _previous_files(output):
    files = {}
    if not output.exists():
        return files
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(output).as_posix()
        if rel == "pubspec.yaml" or rel.startswith(("lib/", "test/")):
            files[rel] = path.read_text(encoding="utf-8")
    return validate_files({"files": files}) if files else {}


def generate_local(instruction: str, output: Path, *, model: str = MODEL,
                   feedback: str | None = None):
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("module instruction must not be empty")
    previous = _previous_files(output)
    if feedback is None and (output.exists() and any(output.iterdir())):
        raise ValueError("output directory must start empty")
    if feedback is not None and not previous:
        raise ValueError("cannot repair missing original model output")
    if feedback is not None and not feedback.strip():
        raise ValueError("repair requires actual compiler or consumer diagnostics")
    messages = [
        {"role": "system", "content":
            "You create NEW runnable PURE DART packages, not explanations. "
            "Return ONLY JSON in the form {\"files\":{\"pubspec.yaml\":\"...\","
            "\"lib/module.dart\":\"...\",\"test/module_test.dart\":\"...\"}}. "
            "Every file must contain its COMPLETE source, with no Markdown. "
            "pubspec.yaml MUST use 'name:', 'environment: sdk:', and "
            "'dev_dependencies: test: ^1.25.0'. NEVER use 'package:test:' "
            "inside pubspec.yaml and NEVER import test packages in lib/. "
            "No dependencies section with runtime packages. "
            "In lib/, implement EXACTLY the public TOP-LEVEL functions "
            "and signatures named in the user request; never replace them "
            "with static methods or class methods. "
            "Dart records use positional access .$1 and .$2, not .start/.end; "
            "records are immutable and you cannot assign their fields. "
            "Avoid mutating input collections. Keep tests in test/ using "
            "package:test/test.dart and package:<module_name>/<file>.dart. "
            "Do not import test files with relative paths. "
            "No IO, HTTP, shell, subprocesses, FFI or dynamic eval."},
        {"role": "user", "content": instruction},
    ]
    if feedback is not None:
        messages.extend([
            {"role": "assistant", "content": json.dumps(
                {"files": previous}, sort_keys=True)},
            {"role": "user", "content":
                "Your last complete Dart package FAILED real compilation, "
                "Dart tests or an independent application. Fix the cause "
                "without changing the requested public API or skipping "
                "tests. Rewrite ALL package files as JSON files object. "
                "Actual diagnostic (only recent output):\n" +
                feedback[-2500:]},
        ])
    body = json.dumps({
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": "5m",
        "options": {"temperature": 0.1, "seed": 42, "num_predict": 3400},
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, method="POST", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=420) as response:
        if response.status != 200:
            raise RuntimeError("local Ollama model failed")
        reply = json.loads(response.read(2_000_000))
    files = validate_files(json.loads(reply["message"]["content"]))
    output.mkdir(parents=True, exist_ok=True)
    old_metadata = {}
    metadata_path = output / "generation.json"
    if metadata_path.is_file():
        old_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    attempt = int(old_metadata.get("attempt", 0)) + 1 if feedback else 0
    if feedback:
        revisions = output / "revisions"
        revisions.mkdir(exist_ok=True)
        record = {
            "attempt": attempt - 1,
            "files": previous,
            "diagnostic_sha256": _sha(feedback[-2500:]),
        }
        (revisions / f"revision-{attempt - 1}.json").write_text(
            json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    # Replace all model-owned paths; preserve only generation metadata and
    # diagnostic receipts. No path comes from the model except the strict
    # whitelisted file map validated above.
    for rel in previous:
        (output / rel).unlink()
    for relative, source in files.items():
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source, encoding="utf-8")
    metadata_path.write_text(json.dumps({
        "generator": "aivexus-llm-candidate-v1",
        "model": "ollama-local/" + model,
        "provider_endpoint": ENDPOINT,
        "instruction": instruction,
        "status": "UNVALIDATED",
        "inference_backend": "local_open_weight_no_api_key",
        "prompt_eval_count": reply.get("prompt_eval_count"),
        "eval_count": reply.get("eval_count"),
        "attempt": attempt,
        "repair_diagnostic_sha256": _sha(feedback[-2500:]) if feedback else None,
    }, sort_keys=True) + "\n", encoding="utf-8")
    return output
