"""Read-only acquisition of immutable upstream source for discovered intakes.

Never executes upstream code, verifies source bytes through Git objects and
records provenance without advancing testing or certification state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib import error as url_error
from urllib import request as url_request

from library_source_integrity import (
    MAX_LOCAL_PAYLOAD_BYTES,
    MAX_LOCAL_PAYLOAD_FILE_BYTES,
    MAX_LOCAL_PAYLOAD_FILES,
    payload_tree_sha256,
)

REPO = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "MIT-0"}
LICENSE_BASENAMES = {"license", "license.txt", "license.md", "copying", "copying.txt"}


class SourceRecoveryError(ValueError):
    pass


@lru_cache(maxsize=64)
def public_repository_state(repo: str) -> bool:
    """Unauthenticated GitHub visibility check; never use a Library CI token.

    404 means not publicly readable (private, missing, renamed or disabled).
    All other API failures fail closed instead of downgrading a network problem
    into a permanent private-source claim.
    """
    if not isinstance(repo, str) or REPO.fullmatch(repo) is None:
        raise SourceRecoveryError("invalid upstream repository visibility target")
    name = repo.removeprefix("https://github.com/").removesuffix(".git")
    url = f"https://api.github.com/repos/{name}"
    req = url_request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "AI-Orchestrator-Library-Public-Source-Only",
    })
    try:
        with url_request.urlopen(req, timeout=8) as response:
            data = response.read(65537)
    except url_error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise SourceRecoveryError(
            f"cannot verify public visibility (GitHub status {exc.code})"
        ) from exc
    except (url_error.URLError, OSError, TimeoutError) as exc:
        raise SourceRecoveryError("public visibility verification unavailable") from exc
    try:
        if len(data) > 65536:
            raise ValueError("visibility response too large")
        metadata = json.loads(data)
        if not isinstance(metadata, dict):
            raise ValueError("not a repository object")
        if not isinstance(metadata.get("full_name"), str):
            raise ValueError("missing canonical repository name")
        if metadata["full_name"].casefold() != name.casefold():
            raise ValueError("repository moved or identity changed")
        if type(metadata.get("private")) is not bool:
            raise ValueError("repository visibility unknown")
    except (ValueError, TypeError) as exc:
        raise SourceRecoveryError("public visibility metadata invalid") from exc
    return metadata["private"] is False


def _git(directory: Path, *args: str, timeout: int = 90) -> bytes:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    try:
        return subprocess.run(
            ["git", "-C", str(directory), *args],
            check=True, capture_output=True, timeout=timeout, env=env,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise SourceRecoveryError(f"immutable Git operation failed: {args[0]}") from exc


def _safe_path(raw: str) -> Path:
    if not raw or "\\" in raw or "\x00" in raw or raw.startswith("/"):
        raise SourceRecoveryError("invalid upstream path")
    if any(part in {"", ".", "..", ".git"} for part in raw.split("/")):
        raise SourceRecoveryError("unsafe upstream path component")
    pure = PurePosixPath(raw)
    if pure.is_absolute():
        raise SourceRecoveryError("absolute upstream path")
    return Path(*pure.parts)


def _read_manifest(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise SourceRecoveryError("invalid intake manifest")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SourceRecoveryError("invalid intake manifest root")
    return value


def eligible_intakes(root: Path) -> list[Path]:
    candidates = []
    for manifest_path in sorted((root / "intake").glob("*/*/manifest.json")):
        if manifest_path.is_symlink() or manifest_path.parent.is_symlink():
            continue
        data = _read_manifest(manifest_path)
        source = data.get("provenance") or {}
        payload = data.get("payload") or {}
        license_file = source.get("license_file")
        repo = source.get("source_repository")
        sha = source.get("source_commit")
        if (data.get("status") != "discovered"
                or payload.get("type") != "upstream_reference"
                or (manifest_path.parent / "payload").exists()
                or source.get("license") not in PERMISSIVE
                or not isinstance(repo, str) or REPO.fullmatch(repo) is None
                or not isinstance(sha, str) or SHA.fullmatch(sha) is None
                or payload.get("upstream_repository") != repo
                or payload.get("upstream_commit") != sha
                or not isinstance(license_file, str)):
            continue
        try:
            license_path = manifest_path.parent / _safe_path(license_file)
            if (license_path.is_symlink() or not license_path.is_file()
                    or manifest_path.parent.resolve() not in license_path.resolve().parents
                    or license_path.stat().st_size == 0):
                continue
        except (OSError, SourceRecoveryError):
            continue
        candidates.append(manifest_path)
    # Third-party Researcher discoveries first, then existing first-party intake.
    # Sort keys are determined solely by immutable manifest metadata.
    candidates.sort(key=lambda p: (
        (json.loads(p.read_text(encoding="utf-8")).get("provenance") or {})
        .get("source_repository", "").startswith("https://github.com/pilialvu75-hue/"),
        p.as_posix(),
    ))
    return candidates


def acquire(manifest_path: Path, *, test_remote: str | None = None) -> dict:
    manifest = _read_manifest(manifest_path)
    base = manifest_path.parent
    provenance = manifest["provenance"]
    payload = manifest["payload"]
    repo, sha = provenance["source_repository"], provenance["source_commit"]
    if (payload.get("type") != "upstream_reference"
            or payload.get("upstream_repository") != repo
            or payload.get("upstream_commit") != sha
            or REPO.fullmatch(repo) is None or SHA.fullmatch(sha) is None
            or provenance.get("license") not in PERMISSIVE
            or (base / "payload").exists()):
        raise SourceRecoveryError("candidate is not eligible for immutable acquisition")

    # The Module Library is public. Never copy private upstream source into
    # a public repository just because a different actor has read access.
    # test_remote is an explicit local-only test fixture, not a manifest field.
    if test_remote is None and not public_repository_state(repo):
        raise SourceRecoveryError("upstream repository is not publicly readable")

    license_path = base / _safe_path(provenance["license_file"])
    if license_path.is_symlink() or not license_path.is_file():
        raise SourceRecoveryError("license evidence missing")
    declared_license = license_path.read_bytes()
    if not declared_license or len(declared_license) > MAX_LOCAL_PAYLOAD_FILE_BYTES:
        raise SourceRecoveryError("license evidence invalid")

    with tempfile.TemporaryDirectory(prefix="library-pinned-source-") as temporary:
        temp = Path(temporary)
        git_dir = temp / "git"
        git_dir.mkdir()
        _git(git_dir, "init", "-q")
        _git(git_dir, "remote", "add", "origin", test_remote or repo)
        _git(git_dir, "-c", "core.hooksPath=/dev/null", "fetch", "-q",
             "--no-tags", "--depth=1", "origin", sha)
        actual = _git(git_dir, "rev-parse", "FETCH_HEAD^{commit}").decode().strip()
        if actual != sha:
            raise SourceRecoveryError("fetched commit differs from pinned provenance")
        tree = _git(git_dir, "rev-parse", "FETCH_HEAD^{tree}").decode().strip()
        entries = _git(git_dir, "ls-tree", "-rz", "--full-tree", "FETCH_HEAD").split(b"\0")
        stage = temp / "payload"
        stage.mkdir()
        count, total = 0, 0
        license_verified = False
        for entry in entries:
            if not entry:
                continue
            try:
                header, raw_path = entry.split(b"\t", 1)
                mode, object_type, object_id = header.decode("ascii").split()
                relative = _safe_path(raw_path.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise SourceRecoveryError("unsafe or invalid Git tree entry") from exc
            if object_type != "blob" or mode not in {"100644", "100755"}:
                raise SourceRecoveryError("symlink, gitlink or non-file source requires review")
            count += 1
            if count > MAX_LOCAL_PAYLOAD_FILES:
                raise SourceRecoveryError("upstream file count exceeds isolation budget")
            size = int(_git(git_dir, "cat-file", "-s", object_id).decode().strip())
            if size > MAX_LOCAL_PAYLOAD_FILE_BYTES or total + size > MAX_LOCAL_PAYLOAD_BYTES:
                raise SourceRecoveryError("upstream source exceeds isolation budget")
            data = _git(git_dir, "cat-file", "blob", object_id)
            if len(data) != size:
                raise SourceRecoveryError("Git blob size mismatch")
            total += size
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if relative.name.lower() in LICENSE_BASENAMES and data == declared_license:
                license_verified = True
        if not count or not license_verified:
            raise SourceRecoveryError("empty source or license bytes differ from immutable upstream")
        digest = payload_tree_sha256(stage)
        target = base / "payload"
        if target.exists() or target.is_symlink():
            raise SourceRecoveryError("concurrent payload acquisition")
        shutil.copytree(stage, target, symlinks=False)
        receipt = {
            "schema": "ai-orchestrator.pinned-source-acquisition.v1",
            "asset_id": manifest["id"],
            "version": manifest["version"],
            "source_repository": repo,
            "source_commit": sha,
            "source_tree": tree,
            "payload_sha256": digest,
            "source_files": count,
            "source_bytes": total,
            "license_bytes_matched": True,
            "executed_upstream_code": False,
            "tests_passed": False,
            "security_reviewed": False,
            "certification_authorized": False,
        }
        evidence = base / "provenance" / "source-acquisition.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["path"] = "payload"
        payload["sha256"] = digest
        payload["acquisition_evidence"] = "provenance/source-acquisition.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidates = eligible_intakes(args.root)
    result = {
        "acquired": False,
        "eligible_count": len(candidates),
        "deferred_nonpublic": [],
        "certification_authorized": False,
    }
    # One actual immutable source acquisition per workflow, but nonpublic
    # repositories must not starve public candidates or fail every daily run.
    for candidate in candidates:
        manifest = _read_manifest(candidate)
        repo = (manifest.get("provenance") or {}).get("source_repository")
        if not public_repository_state(repo):
            result["deferred_nonpublic"].append(
                f"{manifest['id']}@{manifest['version']}"
            )
            continue
        receipt = acquire(candidate)
        result.update({"acquired": True, **receipt})
        break
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
