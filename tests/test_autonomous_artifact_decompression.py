"""Bounded decompression regression for protected evidence artifact ZIP."""
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from tools.autonomous_receipt_evidence_probe import fetch_ci_evidence_artifact


def zipped(data):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ci-evidence.json", data)
    return output.getvalue()


class Response:
    def __init__(self, data):
        self.stream = io.BytesIO(data)

    def geturl(self):
        return "https://api.github.com/repos/owner/repo/actions/artifacts/42/zip"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.stream.read(n)


class ArtifactDecompressionTests(unittest.TestCase):
    def test_valid_small_artifact(self):
        with patch("tools.autonomous_receipt_evidence_probe.urllib.request.urlopen",
                   return_value=Response(zipped(json.dumps({"ok": True})))):
            self.assertEqual(fetch_ci_evidence_artifact("owner/repo", 3, "token"),
                             {"ok": True})

    def test_rejects_expanded_payload_over_limit(self):
        payload = zipped(b" " * 65537)
        with patch("tools.autonomous_receipt_evidence_probe.urllib.request.urlopen",
                   return_value=Response(payload)):
            with self.assertRaisesRegex(ValueError, "size limit"):
                fetch_ci_evidence_artifact("owner/repo", 3, "token")


if __name__ == "__main__":
    unittest.main()
