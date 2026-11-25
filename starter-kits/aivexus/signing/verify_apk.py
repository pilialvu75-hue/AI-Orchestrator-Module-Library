"""Fail-closed Android release identity and integrity gate (no private keys)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def fingerprint(value):
    value = value.strip().replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a SHA-256 certificate fingerprint")
    return value


def validate_identity(badging, certificates, package_id, version_code, previous_code, expected_cert):
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+", package_id):
        raise ValueError("Invalid package ID")
    if not 0 <= previous_code < version_code <= 2100000000:
        raise ValueError("Version code must increase")
    packages = re.findall(r"^package: name='([^']+)' versionCode='(\d+)'", badging, re.M)
    if packages != [(package_id, str(version_code))]:
        raise ValueError("APK package or version mismatch")
    if re.search(r"^application-debuggable\s*$", badging, re.M):
        raise ValueError("Debuggable APK is not eligible for release")
    observed = re.findall(r"^.*?certificate SHA-256 digest:\s*([0-9a-fA-F:]+)\s*$", certificates, re.M)
    if not observed or {fingerprint(x) for x in observed} != {fingerprint(expected_cert)}:
        raise ValueError("APK certificate mismatch or unavailable")


def verify(apk, aapt, apksigner, package_id, code, previous, cert):
    apk = Path(apk)
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        raise ValueError("APK missing")
    # apksigner exit status must be successful; never trust printed fingerprint alone.
    certs = subprocess.run([apksigner, "verify", "--print-certs", str(apk)], check=True, capture_output=True, text=True).stdout
    badging = subprocess.run([aapt, "dump", "badging", str(apk)], check=True, capture_output=True, text=True).stdout
    validate_identity(badging, certs, package_id, code, previous, cert)
    with apk.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return {"package_id": package_id, "version_code": code, "certificate_sha256": fingerprint(cert), "apk_sha256": digest, "apk_size_bytes": apk.stat().st_size}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("apk", "aapt", "apksigner", "package-id", "certificate", "receipt"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--version-code", required=True, type=int)
    p.add_argument("--previous-code", required=True, type=int)
    a = p.parse_args()
    receipt = Path(a.receipt)
    if receipt.exists():
        raise FileExistsError("Refuse to reuse an existing receipt")
    result = verify(a.apk, a.aapt, a.apksigner, a.package_id, a.version_code, a.previous_code, a.certificate)
    with receipt.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
