"""Bounded canonical SHA256 for version-pinned local module source payloads.

This module is deliberately independent of the intake state machine. Both
Dart/CI evidence validation and Cantiere package export must hash precisely
the same source bytes; they cannot rely on a manifest's declaration alone.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

MAX_LOCAL_PAYLOAD_FILES = 512
MAX_LOCAL_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_LOCAL_PAYLOAD_FILE_BYTES = 2 * 1024 * 1024


class SourceIntegrityError(ValueError):
    pass


def _require(value: bool, message: str) -> None:
    if not value:
        raise SourceIntegrityError(message)


def _sha256_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def payload_tree_sha256(source: Path) -> str:
    """Hash relative path lengths, UTF8 paths, and each file's SHA256 bytes.

    The format is compatible with the already pinned Library repository_path
    v1 manifests. Symlinks, missing/empty payloads, files above 2 MiB, trees
    above 16 MiB or with more than 512 files fail closed.
    """
    _require(source.exists() and not source.is_symlink(),
             "repository_path must point to a real non-symlink payload")
    if source.is_file():
        root, candidates = source.parent, [source]
    else:
        _require(source.is_dir(), "repository_path payload must be a file or directory")
        root = source
        candidates = sorted(source.rglob("*"), key=lambda p: p.as_posix())
    _require(bool(candidates), "repository_path payload must contain at least one file")
    digest = hashlib.sha256()
    file_count = 0
    total = 0
    for item in candidates:
        _require(not item.is_symlink(), "repository_path payload may not contain symlinks")
        if item.is_dir():
            continue
        _require(item.is_file(), "repository_path contains a non-file entry")
        file_count += 1
        _require(file_count <= MAX_LOCAL_PAYLOAD_FILES,
                 "repository_path payload exceeds file count limit")
        size = item.stat().st_size
        _require(size <= MAX_LOCAL_PAYLOAD_FILE_BYTES,
                 "repository_path payload contains an oversized file")
        total += size
        _require(total <= MAX_LOCAL_PAYLOAD_BYTES,
                 "repository_path payload exceeds total size limit")
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(_sha256_file(item))
    _require(file_count > 0, "repository_path payload must contain at least one file")
    return digest.hexdigest()
