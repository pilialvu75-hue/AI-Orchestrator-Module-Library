"""Negative and positive tests for the bounded GitHub Actions artifact reader."""
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from tools.autonomous_receipt_evidence_probe import fetch_ci_evidence_artifact


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return stream.getvalue()


class Response:
    def __init__(self, data):
        self.data = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        return self.data.read(size)


class ArtifactZipTests(unittest.TestCase):
    def read(self, data):
        with patch("tools.autonomous_receipt_evidence_probe.urllib.request.urlopen",
                   return_value=Response(data)):
            return fetch_ci_evidence_artifact("owner/repo", 42, "test-token")

    def test_valid_json_object(self):
        self.assertEqual(self.read(zipped([("ci-evidence.json", '{"ok":true}')])),
                         {"ok": True})

    def test_rejects_bad_zip_and_unexpected_entries(self):
        cases = (
            b"not-a-zip",
            zipped([]),
            zipped([("../ci-evidence.json", "{}")]),
            zipped([("ci-evidence.json", "{}"), ("other.json", "{}")]),
            zipped([("ci-evidence.json", "[]")]),
            zipped([("ci-evidence.json", "invalid-json")]),
            zipped([("ci-evidence.json", "x" * 65537)]),
            b"x" * 262145,
        )
        for data in cases:
            with self.subTest(size=len(data)):
                with self.assertRaises(ValueError):
                    self.read(data)

    def test_rejects_invalid_fetch_arguments_without_network(self):
        with patch("tools.autonomous_receipt_evidence_probe.urllib.request.urlopen") as urlopen:
            for repo, artifact_id, token in (
                ("../repo", 42, "token"),
                ("owner/repo", True, "token"),
                ("owner/repo", 0, "token"),
                ("owner/repo", 42, ""),
            ):
                with self.subTest(repo=repo, artifact_id=artifact_id):
                    with self.assertRaises(ValueError):
                        fetch_ci_evidence_artifact(repo, artifact_id, token)
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
