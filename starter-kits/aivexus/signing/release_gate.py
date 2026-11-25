"""Opt-in Android release pipeline for public repositories; no key generation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from verify_apk import verify, fingerprint

CONFIG = Path("signing/release-config.json")


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def inputs():
    cfg = json.loads(CONFIG.read_text())
    if cfg.get("channel") != "stable" or cfg.get("distribution") != "public-github-releases":
        raise ValueError("Only explicitly configured public stable distribution is supported")
    if cfg.get("manifest_path") != "update/version.json":
        raise ValueError("Unexpected manifest path")
    fingerprint(cfg["certificate_sha256"])
    version = os.environ["VERSION"]
    code = int(os.environ["VERSION_CODE"])
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Version must be x.y.z")
    path = Path(cfg["manifest_path"])
    # Explicit initial manifest is required, no implicit reset to zero.
    previous = json.loads(path.read_text())
    old = previous["versionCode"]
    if type(old) is not int or not 0 <= old < code <= 2100000000:
        raise ValueError("versionCode must increase")
    if old > 0 and tuple(map(int, version.split("."))) <= tuple(map(int, previous["version"].split("."))):
        raise ValueError("Version name must increase")
    return cfg, version, code, old


def restore_key(path):
    names = ("ANDROID_KEYSTORE_B64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD")
    if any(not os.environ.get(name) for name in names):
        raise ValueError("Missing permanent Android signing secret; refusing replacement")
    data = base64.b64decode(os.environ[names[0]], validate=True)
    if not data:
        raise ValueError("Empty keystore")
    Path(path).write_bytes(data)


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def remote_manifest(repo, path):
    data = json.loads(run("gh", "api", f"repos/{repo}/contents/{path}?ref=main"))
    return data["sha"], json.loads(base64.b64decode(data["content"]))


def confirm_receipt(receipt, apk, cfg, code):
    if receipt["package_id"] != cfg["package_id"] or receipt["version_code"] != code:
        raise ValueError("Receipt identity mismatch")
    if fingerprint(receipt["certificate_sha256"]) != fingerprint(cfg["certificate_sha256"]):
        raise ValueError("Receipt certificate mismatch")
    if receipt["apk_sha256"] != digest(apk) or receipt["apk_size_bytes"] != Path(apk).stat().st_size:
        raise ValueError("Receipt asset digest or size mismatch")


def publish(directory):
    cfg, version, code, old = inputs()
    repo = os.environ["GITHUB_REPOSITORY"]
    source = os.environ["SOURCE_SHA"]
    if run("gh", "api", f"repos/{repo}", "--jq", ".private") != "false":
        raise ValueError("Refusing private-repository publication; configure a separate approved feed")
    if run("gh", "api", f"repos/{repo}/git/ref/heads/main", "--jq", ".object.sha") != source:
        raise ValueError("Main changed; rebuild before publication")
    manifest_path = cfg["manifest_path"]
    blob, previous = remote_manifest(repo, manifest_path)
    if previous["versionCode"] != old:
        raise ValueError("Published version changed; rebuild")
    directory = Path(directory)
    apk = directory / "app-release.apk"
    receipt = json.loads((directory / "receipt.json").read_text())
    confirm_receipt(receipt, apk, cfg, code)
    tag = "v" + version
    # Never overwrite an existing release or asset. A failed run may require owner review.
    subprocess.run(["gh", "release", "create", tag, str(apk), "--repo", repo,
                    "--target", source, "--title", version, "--notes", "Verified Android release", "--draft"], check=True)
    subprocess.run(["gh", "release", "edit", tag, "--repo", repo, "--draft=false"], check=True)
    url = f"https://github.com/{repo}/releases/download/{tag}/app-release.apk"
    with tempfile.TemporaryDirectory() as temp:
        downloaded = Path(temp) / "app-release.apk"
        # No GitHub token or authorization header for the public client path.
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location",
                        "--proto", "=https", "--proto-redir", "=https", "--output", str(downloaded), url], check=True)
        confirm_receipt(receipt, downloaded, cfg, code)
    if remote_manifest(repo, manifest_path)[0] != blob:
        raise ValueError("Manifest changed during release; not publishing")
    manifest = {"version": version, "versionCode": code, "channel": "stable",
                "min_supported": previous.get("min_supported", "0.0.0"),
                "apk_url": url, "apk_file_name": "app-release.apk",
                "apk_sha256": receipt["apk_sha256"], "apk_size_bytes": receipt["apk_size_bytes"],
                "changelog": "Verified Android release", "critical": False}
    payload = {"message": f"Publish verified Android manifest {version}", "sha": blob,
               "branch": "main", "content": base64.b64encode((json.dumps(manifest, indent=2) + "\n").encode()).decode()}
    subprocess.run(["gh", "api", "--method", "PUT", f"repos/{repo}/contents/{manifest_path}", "--input", "-"],
                   input=json.dumps(payload), text=True, check=True)


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    if action == "preflight":
        inputs()
    elif action == "restore-key":
        restore_key(args[0])
    elif action == "verify":
        cfg, version, code, old = inputs()
        sdk, apk, receipt = args
        result = verify(apk, str(Path(sdk) / "aapt"), str(Path(sdk) / "apksigner"),
                        cfg["package_id"], code, old, cfg["certificate_sha256"])
        with Path(receipt).open("x") as f:
            json.dump(result, f, indent=2)
    elif action == "publish":
        publish(args[0])
    else:
        raise ValueError("Unknown action")
