"""Protected merger must never infer production approval from CI green."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from autonomous_public_dart_merger import candidate, has_required_checks  # noqa: E402


def pr(package="path", ref=None):
    return {
        "state": "open", "mergeable": True,
        "title": f"Researcher autonomous source: {package} (sandbox only, not certified)",
        "head": {"ref": ref or "researcher/public-dart-" + package,
                 "sha": "a"*40,
                 "repo": {"full_name": "pilialvu75-hue/AI-Orchestrator-Module-Library"}},
        "base": {"ref": "main"},
    }


def files(package="path"):
    root = "sandbox/researcher_public_dart/" + package + "/"
    return [{"filename": root + "metadata.json", "status": "added"},
            {"filename": root + "payload/src/vendor/" + package + "/LICENSE",
             "status": "added"},
            {"filename": root + "payload/src/tool/self_test.dart",
             "status": "added"}]


def passes(name, sha="a"*40, outcome="success", event="pull_request"):
    return {"name": name, "head_sha": sha, "status": "completed",
            "conclusion": outcome, "event": event}


class ProtectedResearcherMergeTests(unittest.TestCase):
    def test_safe_sandbox_candidate_only(self):
        self.assertEqual("path", candidate(pr(), files()))
        self.assertIsNone(candidate(pr(), files()+[{"filename": "catalog/index.json",
                                                    "status": "modified"}]))
        self.assertIsNone(candidate(pr(), files()+[{"filename": "tools/run.py",
                                                    "status": "modified"}]))
        self.assertIsNone(candidate(pr(), files()[1:]))
        self.assertIsNone(candidate(pr(), [{"filename": "sandbox/researcher_public_dart/path/metadata.json",
                                           "status": "removed"}]))

    def test_untrusted_refs_and_cross_repo_never_merge(self):
        obj = pr()
        obj["head"]["repo"]["full_name"] = "other/repository"
        self.assertIsNone(candidate(obj, files()))
        obj = pr(ref="researcher/public-dart-path-foo")
        self.assertIsNone(candidate(obj, files()))
        obj = pr()
        obj["mergeable"] = None
        self.assertIsNone(candidate(obj, files()))
        obj = pr()
        obj["base"]["ref"] = "release"
        self.assertIsNone(candidate(obj, files()))

    def test_both_independent_validations_same_head_mandatory(self):
        checks = [passes("Validate Module Library"),
                  passes("Library isolated verification of Researcher public Dart intake")]
        self.assertTrue(has_required_checks(checks, "a"*40))
        self.assertFalse(has_required_checks(checks[:1], "a"*40))
        self.assertFalse(has_required_checks(checks, "b"*40))
        checks[1]["conclusion"] = "failure"
        self.assertFalse(has_required_checks(checks, "a"*40))
        checks[1]["conclusion"] = "success"
        checks[1]["event"] = "push"
        self.assertFalse(has_required_checks(checks, "a"*40))


if __name__ == "__main__":
    unittest.main()
