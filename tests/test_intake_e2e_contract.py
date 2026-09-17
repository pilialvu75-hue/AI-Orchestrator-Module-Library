from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_intake_bundle import IntakeBundleError, materialize_bundle, verify_bundle_bytes


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_bundle(asset_id: str = "example.echo", version: str = "1.0.0") -> tuple[bytes, str]:
    payload = {
        "schema": "ai-orchestrator.library-intake-payload.v1",
        "files": [
            {
                "path": "lib/echo.dart",
                "content_base64": base64.b64encode(b"String echo(String value) => value;\n").decode("ascii"),
            }
        ],
    }
    payload_json = canonical_json(payload)
    payload_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    payload_path = "payload/source.json"
    manifest = {
        "id": asset_id,
        "version": version,
        "status": "discovered",
        "payload": {"type": "archive", "path": payload_path, "sha256": payload_sha},
    }
    bundle = {
        "schema": "ai-orchestrator.library-intake-bundle.v1",
        "pin": f"{asset_id}@{version}",
        "manifest_path": f"intake/{asset_id}/{version}/manifest.json",
        "payload_path": payload_path,
        "payload_sha256": payload_sha,
        "payload_json": payload_json,
        "manifest": manifest,
    }
    raw = canonical_json(bundle).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


class IntakeEndToEndContractTest(unittest.TestCase):
    def test_verified_bundle_materializes_idempotently(self) -> None:
        raw, digest = build_bundle()
        verified = verify_bundle_bytes(raw, digest)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = materialize_bundle(root, verified)
            second = materialize_bundle(root, verified)
            self.assertEqual(first, second)
            self.assertEqual(json.loads((first / "manifest.json").read_text()), verified.manifest)
            self.assertEqual((first / verified.payload_path).read_text(), verified.payload_json)

    def test_transport_digest_is_fail_closed(self) -> None:
        raw, _ = build_bundle()
        with self.assertRaisesRegex(IntakeBundleError, "bundle sha256 mismatch"):
            verify_bundle_bytes(raw, "0" * 64)

    def test_divergent_replay_is_rejected(self) -> None:
        raw, digest = build_bundle()
        verified = verify_bundle_bytes(raw, digest)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = materialize_bundle(root, verified)
            (destination / "manifest.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(IntakeBundleError, "divergent content"):
                materialize_bundle(root, verified)

    def test_secret_like_payload_path_is_rejected(self) -> None:
        raw, digest = build_bundle()
        bundle = json.loads(raw)
        payload = json.loads(bundle["payload_json"])
        payload["files"][0]["path"] = ".env"
        bundle["payload_json"] = canonical_json(payload)
        bundle["payload_sha256"] = hashlib.sha256(bundle["payload_json"].encode()).hexdigest()
        bundle["manifest"]["payload"]["sha256"] = bundle["payload_sha256"]
        tampered = canonical_json(bundle).encode()
        tampered_digest = hashlib.sha256(tampered).hexdigest()
        with self.assertRaisesRegex(IntakeBundleError, "unsafe payload file path"):
            verify_bundle_bytes(tampered, tampered_digest)


if __name__ == "__main__":
    unittest.main()
