"""Needs-only autonomous scope decisions from independently fetched GitHub data."""
import unittest
from unittest.mock import patch

from tools.autonomous_needs_scope import verify_needs_only_scope
from tools.autonomous_independent_gates import LIBRARY_REPOSITORY as REPO

SHA = "a" * 40
BLOB = "b" * 40
IDENTITY = {
    "lane_id": "library-curation", "state_version": 9,
    "claim_id": "claim", "packet_sha256": "c" * 64,
    "repository": REPO, "pr_number": 120, "head_sha": SHA,
}
PR = {"number": 120, "state": "open", "draft": False,
      "base": {"repo": {"full_name": REPO}, "ref": "main"},
      "head": {"repo": {"full_name": REPO}, "sha": SHA}}
FILE = {"filename": "catalog/needs.json", "status": "modified",
        "sha": BLOB, "changes": 3}
CONTENT = {"path": "catalog/needs.json", "type": "file", "sha": BLOB}


class SafeNeedsScopeTests(unittest.TestCase):
    def probe(self, *, files=None, content=None, pr=None, latest=None):
        data = [
            PR if pr is None else pr,
            [FILE] if files is None else files,
            CONTENT if content is None else content,
            PR if latest is None else latest,
        ]
        with patch("tools.autonomous_needs_scope.fetch_json", side_effect=data) as fetch:
            result = verify_needs_only_scope(IDENTITY, "test-token")
        return result, fetch

    def test_only_one_needs_metadata_change_can_qualify(self):
        scope, fetch = self.probe()
        self.assertEqual(fetch.call_count, 4)
        self.assertTrue(scope["scope_verified"])
        self.assertFalse(scope["runtime_applicable"])
        self.assertFalse(scope["executable_changes"])
        self.assertEqual(scope["canonical_identity"], IDENTITY)

    def test_rejects_code_or_multiple_changed_files(self):
        cases = ([], [FILE, {**FILE, "filename": "tools/unsafe.py"}],
                 [{**FILE, "filename": "modules/new/code.dart"}],
                 [{**FILE, "filename": "catalog/index.json"}],
                 [{**FILE, "status": "added"}],
                 [{**FILE, "status": "renamed", "previous_filename": "old.json"}],
                 [{**FILE, "sha": "invalid"}],
                 [{**FILE, "changes": True}])
        for files in cases:
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.probe(files=files)

    def test_rejects_changed_blob_or_head(self):
        for item in ({**CONTENT, "sha": "f" * 40},
                     {**CONTENT, "type": "symlink"},
                     {**CONTENT, "path": "catalog/index.json"}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.probe(content=item)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.probe(latest={**PR, "head": {**PR["head"], "sha": "f" * 40}})

    def test_rejects_fork_draft_nonmain_or_closed_pr(self):
        cases = (
            {**PR, "draft": True},
            {**PR, "state": "closed"},
            {**PR, "base": {"ref": "other", "repo": {"full_name": REPO}}},
            {**PR, "head": {"sha": SHA, "repo": {"full_name": "attacker/fork"}}},
        )
        for pr in cases:
            with self.subTest(pr=pr), self.assertRaises(ValueError):
                self.probe(pr=pr)

    def test_rejects_out_of_scope_identity_without_network(self):
        for value in ({**IDENTITY, "repository": "other/repo"},
                      {**IDENTITY, "pr_number": True},
                      {**IDENTITY, "head_sha": "invalid"}):
            with self.subTest(identity=value), patch(
                "tools.autonomous_needs_scope.fetch_json"
            ) as fetch:
                with self.assertRaises(ValueError):
                    verify_needs_only_scope(value, "test-token")
                fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
