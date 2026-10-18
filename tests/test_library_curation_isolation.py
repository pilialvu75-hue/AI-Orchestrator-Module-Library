"""A Researcher handoff cannot occupy or authorize Library curation work."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools import control_plane_manager
from tools.autonomous_needs_scope import verify_needs_only_scope
from tools.control_plane_inbox import _independently_verify_needs_completion

ROOT = Path(__file__).resolve().parents[1]
REPO = "pilialvu75-hue/AI-Orchestrator-Module-Library"
CURATION = ".airlab/control-plane/workstreams/library-curation.json"
RESEARCHER = ".airlab/control-plane/workstreams/library-researcher.json"


class LibraryCurationIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / ".airlab", self.root / ".airlab")

    def test_curator_claim_does_not_modify_researcher_claim_or_packet(self):
        researcher_before = (self.root / RESEARCHER).read_bytes()
        now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        claim_id = control_plane_manager.claim(
            "library-curation", "library-needs-safe-curation-01", REPO,
            "One bounded catalog/needs.json quality improvement",
            branch="feat/library-needs-curation-01",
            resource_locks=["file:" + REPO + ":catalog/needs.json"],
            root=self.root, now=now,
        )
        curation = json.loads((self.root / CURATION).read_text())
        self.assertEqual(curation["active_claim"]["claim_id"], claim_id)
        self.assertEqual(curation["status"], "CLAIMED")
        self.assertEqual(curation["gates"]["G6_REVIEWER"], "PENDING")
        self.assertEqual((self.root / RESEARCHER).read_bytes(), researcher_before)
        registry = json.loads((self.root / ".airlab/control-plane/chat-registry.json").read_text())
        entries = {item["id"]: item for item in registry["lanes"]}
        self.assertEqual(entries["library-curation"]["primary_repository"], REPO)
        self.assertEqual(entries["library-researcher"]["secondary_repositories"],
                         ["pilialvu75-hue/AI-Orchestrator-Module-Researcher"])

    def test_old_researcher_lane_cannot_use_needs_only_completion(self):
        with patch("tools.autonomous_needs_scope.fetch_json") as fetch:
            with self.assertRaisesRegex(ValueError, "exact Library PR"):
                verify_needs_only_scope({
                    "lane_id": "library-researcher", "repository": REPO,
                    "pr_number": 120, "head_sha": "a" * 40,
                }, "fake-token")
            fetch.assert_not_called()

    def test_old_researcher_lane_cannot_invoke_protected_needs_inbox(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with self.assertRaisesRegex(ValueError, "limited to the Library worker lane"):
                _independently_verify_needs_completion(
                    self.root, "library-researcher",
                    {"protected_run_id": 123, "run_attempt": 1,
                     "protected_sha": "a" * 40},
                    now=datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
