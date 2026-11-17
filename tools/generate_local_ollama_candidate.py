#!/usr/bin/env python3
"""Generate a genuine Dart package with a local open-weight model (Ollama).

The only inference endpoint is loopback. No API keys, remote model providers,
prewritten Dart code or fallback templates. Source is UNVALIDATED until a
separate real Dart/consumer check succeeds.
"""
import json
from pathlib import Path
import urllib.request

from generate_llm_dart_candidate import validate_files

ENDPOINT = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5-coder:3b"


def generate_local(instruction: str, output: Path, *, model: str = MODEL):
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("module instruction must not be empty")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must start empty")
    request = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": "5m",
        "options": {"temperature": 0.1, "seed": 42, "num_predict": 2300},
        "messages": [
            {"role": "system", "content":
                "You write new, runnable PURE DART modules. Return ONLY a "
                "valid JSON object of the form {\"files\": {\"pubspec.yaml\": "
                "\"...\", \"lib/name.dart\": \"...\", "
                "\"test/name_test.dart\": \"...\"}}. "
                "Each file must contain complete source, not Markdown fences. "
                "Use Dart >=3.3.0, only package:test as a dev dependency, "
                "no runtime dependencies, subprocesses, IO, network, FFI, "
                "or shell commands. Use exactly the public names and paths "
                "in the user specification. Write behavioral Dart tests."},
            {"role": "user", "content": instruction},
        ],
    }
    body = json.dumps(request).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, method="POST", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=400) as response:
        if response.status != 200:
            raise RuntimeError("local model failed")
        reply = json.loads(response.read(1_500_000))
    content = reply["message"]["content"]
    files = validate_files(json.loads(content))
    output.mkdir(parents=True, exist_ok=True)
    for relative, source in files.items():
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source, encoding="utf-8")
    (output / "generation.json").write_text(
        json.dumps({
            "generator": "aivexus-llm-candidate-v1",
            "model": "ollama-local/" + model,
            "provider_endpoint": ENDPOINT,
            "instruction": instruction,
            "status": "UNVALIDATED",
            "inference_backend": "local_open_weight_no_api_key",
            "prompt_eval_count": reply.get("prompt_eval_count"),
            "eval_count": reply.get("eval_count"),
        }, sort_keys=True) + "\n", encoding="utf-8",
    )
    return output
