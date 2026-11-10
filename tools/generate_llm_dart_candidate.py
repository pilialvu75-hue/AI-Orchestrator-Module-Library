#!/usr/bin/env python3
"""Generate a Dart module from a real OpenAI-compatible LLM response.

This is an experimental candidate generator, not a certification pipeline.
Never execute model-provided shell commands or arbitrary file paths.
"""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.request

_ALLOWED = re.compile(r"^(pubspec\.yaml|lib/[a-z][a-z0-9_]*\.dart|test/[a-z][a-z0-9_]*_test\.dart)$")
_MAX_FILE_BYTES = 100_000


def validate_files(payload):
    if not isinstance(payload, dict) or set(payload) != {"files"}:
        raise ValueError("model response must contain only files")
    files = payload["files"]
    if not isinstance(files, dict) or not 3 <= len(files) <= 20:
        raise ValueError("expected 3 to 20 files")
    if "pubspec.yaml" not in files or not any(p.startswith("lib/") for p in files) or not any(p.startswith("test/") for p in files):
        raise ValueError("pubspec, library and tests required")
    for path, content in files.items():
        if not isinstance(path, str) or not _ALLOWED.fullmatch(path):
            raise ValueError("disallowed output path")
        if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > _MAX_FILE_BYTES:
            raise ValueError("invalid file content")
    return files


def generate(instruction, output, *, endpoint, model, api_key):
    if not instruction.strip():
        raise ValueError("instruction is empty")
    if not api_key or not model or not endpoint.startswith("https://"):
        raise ValueError("HTTPS endpoint, model and API key required")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    request_body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Write a reusable pure-Dart package for the user requirement. Return ONLY a JSON object with key files mapping paths to complete source strings. Include pubspec.yaml, lib/*.dart, test/*_test.dart. No external dependencies beyond Dart test. No scripts, network calls or shell commands."},
            {"role": "user", "content": instruction},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=request_body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError("model provider returned non-200")
        result = json.loads(response.read(1_000_000))
    answer = result["choices"][0]["message"]["content"]
    files = validate_files(json.loads(answer))
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (output / "generation.json").write_text(json.dumps({
        "generator": "aivexus-llm-candidate-v1",
        "model": model,
        "provider_endpoint": endpoint.split("/v1/")[0],
        "instruction": instruction,
        "status": "UNVALIDATED",
    }, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate(args.instruction, args.output,
             endpoint=os.getenv("MODULE_LLM_ENDPOINT", ""),
             model=os.getenv("MODULE_LLM_MODEL", ""),
             api_key=os.getenv("MODULE_LLM_API_KEY", ""))


if __name__ == "__main__":
    main()
