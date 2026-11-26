import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from release_gate import restore_key, confirm_receipt

CERT = "ab" * 32
CFG = {"package_id": "com.aivexus.demo", "certificate_sha256": CERT}

class ReleaseTests(unittest.TestCase):
    def test_no_secrets_no_replacement_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key.p12"
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
                restore_key(path)
            self.assertFalse(path.exists())

    def test_tampered_asset_never_matches_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.apk"
            path.write_bytes(b"original")
            receipt = {"package_id": CFG["package_id"], "version_code": 2, "certificate_sha256": CERT,
                       "apk_sha256": hashlib.sha256(b"original").hexdigest(), "apk_size_bytes": 8}
            confirm_receipt(receipt, path, CFG, 2)
            path.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                confirm_receipt(receipt, path, CFG, 2)
