#!/usr/bin/env python3
"""Real open-weight inference for ORIGINAL Dart library code, plus neutral packaging.

Unlike the failed #44135756635 run, Qwen writes only the *functional lib*
source. A generic deterministic packaging shell and the *independently
specified* acceptance tests are never authored by the model. No hand-written
logic or fallback implementation of either requested capability is included.
"""
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from generate_llm_dart_candidate import validate_files

ENDPOINT = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5-coder:3b"
_NAME = re.compile(r"[a-z][a-z0-9_]{1,64}\Z")
_LIB = re.compile(r"lib/[a-z][a-z0-9_]*[.]dart\Z")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _independent_dart_test(consumer_source):
    """Wrap the pre-authored real consumer acceptance body in Dart's test()."""
    start = "void main() {"
    if consumer_source.count(start) != 1 or not consumer_source.rstrip().endswith("}"):
        raise ValueError("independent contract must have a single main() body")
    imports, original = consumer_source.split(start, 1)
    body = original.rstrip()[:-1]
    return (imports +
            "import 'package:test/test.dart';\n"
            "void main() {\n"
            "  test('independent contract, not model-authored', () {\n" +
            body + "\n"
            "  });\n"
            "}\n")


def _previous_files(output):
    if not output.exists():
        return {}
    files = {}
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(output).as_posix()
        if rel == "pubspec.yaml" or rel.startswith(("lib/", "test/")):
            files[rel] = path.read_text(encoding="utf-8")
    return validate_files({"files": files}) if files else {}


def generate_local(instruction: str, output: Path, *,
                   package_name: str, library_path: str,
                   acceptance_source: str, model: str = MODEL,
                   feedback: str | None = None):
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("module instruction must not be empty")
    if _NAME.fullmatch(package_name) is None or _LIB.fullmatch(library_path) is None:
        raise ValueError("invalid independent package name/path")
    acceptance_test = _independent_dart_test(acceptance_source)
    previous = _previous_files(output)
    if feedback is None and output.exists() and any(output.iterdir()):
        raise ValueError("generation directory must start empty")
    if feedback is not None and (not feedback.strip() or library_path not in previous):
        raise ValueError("repair needs existing model source and real diagnostics")
    messages = [
        {"role": "system", "content":
            "You write one original, compilable PURE DART LIBRARY SOURCE FILE. "
            "Return ONLY valid JSON with EXACTLY one key: "
            "{\"source\":\"complete Dart code for the specified lib file\"}. "
            "Do NOT write pubspec, tests, Markdown or file paths. "
            "Implement EXACTLY the requested public TOP-LEVEL function(s), "
            "not static/class methods. Dart positional records use .$1 and "
            ".$2, never .start or .end. Record fields are immutable; create "
            "replacement records rather than editing one. Do NOT mutate "
            "the provided input list. No imports except dart:core, dart:math, "
            "dart:collection or dart:convert. Do not use package:test in lib. "
            "No IO, network, shell, FFI or subprocess execution."},
        {"role": "user", "content": instruction},
    ]
    if feedback is not None:
        messages.extend([
            {"role": "assistant", "content": json.dumps(
                {"source": previous[library_path]}, ensure_ascii=False)},
            {"role": "user", "content":
                "The previous Dart source FAILED actual compiler, functional "
                "tests or an independent Dart consumer. Rewrite the complete "
                "source in the SAME JSON format. Fix every error below and "
                "preserve the exact public function signatures and behavior. "
                "Do not omit functions, use stubs or skip behavior.\n" +
                feedback[-2400:]},
        ])
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({
            "model": model, "stream": False, "format": "json",
            "keep_alive": "5m",
            "options": {"temperature": 0.1, "seed": 42, "num_predict": 1800},
            "messages": messages,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=350) as response:
        if response.status != 200:
            raise RuntimeError("local Ollama inference failed")
        reply = json.loads(response.read(1_500_000))
    raw = reply["message"]["content"]
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"source"}:
            raise ValueError("model must return exactly one Dart source")
        source = data["source"]
        if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > 50000:
            raise ValueError("empty or oversized model Dart source")
    except (ValueError, TypeError):
        # Keep the evidence even when the model produces invalid JSON.
        output.mkdir(parents=True, exist_ok=True)
        (output / "invalid-model-response.txt").write_text(
            raw[:50000], encoding="utf-8")
        raise
    output.mkdir(parents=True, exist_ok=True)
    prior = {}
    metadata = output / "generation.json"
    if metadata.is_file():
        prior = json.loads(metadata.read_text(encoding="utf-8"))
    attempt = int(prior.get("attempt", 0)) + 1 if feedback else 0
    if feedback:
        records = output / "revisions"
        records.mkdir(exist_ok=True)
        (records / f"revision-{attempt - 1}.json").write_text(
            json.dumps({
                "attempt": attempt - 1,
                "source": previous[library_path],
                "diagnostic_sha256": _sha(feedback[-2400:]),
            }, sort_keys=True) + "\n", encoding="utf-8")
    # All generated behavior lives in the ONE LLM-authored library file.
    # Pubspec and test are generic shells around a pre-authored independent
    # acceptance contract, with no implementation of the requested logic.
    files = {
        "pubspec.yaml": (
            f"name: {package_name}\n"
            "version: 0.1.0\n"
            "publish_to: none\n"
            "environment:\n  sdk: '>=3.3.0 <4.0.0'\n"
            "dev_dependencies:\n  test: ^1.25.0\n"
        ),
        library_path: source,
        "test/independent_contract_test.dart": acceptance_test,
    }
    validate_files({"files": files})
    for rel in previous:
        (output / rel).unlink()
    for rel, contents in files.items():
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    metadata.write_text(json.dumps({
        "generator": "aivexus-llm-candidate-v1",
        "model": "ollama-local/" + model,
        "provider_endpoint": ENDPOINT,
        "instruction": instruction,
        "status": "UNVALIDATED",
        "inference_backend": "local_open_weight_no_api_key",
        "prompt_eval_count": reply.get("prompt_eval_count"),
        "eval_count": reply.get("eval_count"),
        "attempt": attempt,
        "code_source_sha256": _sha(source),
        "packaging": "deterministic, no functional implementation",
        "acceptance": "independently pre-authored contract",
        "repair_diagnostic_sha256": _sha(feedback[-2400:]) if feedback else None,
    }, sort_keys=True) + "\n", encoding="utf-8")
    return output
