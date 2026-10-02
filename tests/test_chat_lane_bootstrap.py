import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "chat_lane_bootstrap",
    ROOT / "tools" / "chat_lane_bootstrap.py",
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class ChatLaneBootstrapTests(unittest.TestCase):
    def test_registry_covers_all_canonical_workstreams(self):
        canonical = json.loads((ROOT / ".airlab/control-plane/canonical-state.json").read_text(encoding="utf-8"))
        registered = {entry["id"] for entry in bootstrap.registry(ROOT)["lanes"]}
        workstream_ids = set()
        for rel in canonical["workstreams"]:
            lane = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            workstream_ids.add(lane["id"])
        self.assertEqual(registered, workstream_ids)

    def test_worker_bootstrap_enforces_review_ceiling(self):
        text = bootstrap.build_prompt("voice-live", ROOT)
        self.assertIn("maximum self-declared state is REVIEW_REQUIRED", text)
        self.assertIn("Do not self-promote VERIFIED or DONE", text)
        self.assertIn("workstreams/voice-live.json", text)

    def test_reviewer_bootstrap_has_promotion_authority(self):
        text = bootstrap.build_prompt("main-reviewer", ROOT)
        self.assertIn("canonical promotion authority", text)
        self.assertIn("UNKNOWN remains UNKNOWN", text)

    def test_platform_bootstrap_mentions_target_specific_inference(self):
        text = bootstrap.build_prompt("platform-windows", ROOT)
        self.assertIn("benchmark-gated target profile", text)
        self.assertIn("may differ from every other platform", text)

    def test_bootstrap_requires_continuous_checkpointing(self):
        text = bootstrap.build_prompt("cantiere", ROOT)
        self.assertIn("Do not wait for the chat to become full", text)
        self.assertIn("tools/chat_checkpoint.py", text)
        self.assertIn("last_checkpoint=", text)

    def test_reviewer_bootstrap_reads_raw_review_inbox(self):
        text = bootstrap.build_prompt("main-reviewer", ROOT)
        self.assertIn("projection.review_required is an index, not reviewer authority", text)
        self.assertIn("review-inbox", text)
        self.assertIn("review-accept", text)
        self.assertIn("review-rework", text)

    def test_worker_bootstrap_forbids_status_only_review_handoff(self):
        text = bootstrap.build_prompt("cantiere", ROOT)
        self.assertIn("Never set REVIEW_REQUIRED by editing only the status field", text)
        self.assertIn("submit-review", text)

    def test_bootstrap_requires_resource_lock_declaration(self):
        text = bootstrap.build_prompt("cantiere", ROOT)
        self.assertIn("Declare machine-readable resource_locks", text)
        self.assertIn("overlapping lock is forbidden", text)
        self.assertIn("resource lock owned by another lane", text)

    def test_bootstrap_requires_transactional_mutation_inbox(self):
        text = bootstrap.build_prompt("cantiere", ROOT)
        self.assertIn("TRANSACTIONAL MUTATION RULE", text)
        self.assertIn(".airlab/control-plane/inbox/pending/", text)
        self.assertIn("expected_state_version", text)
        self.assertIn("never edit workstream JSON or canonical-state.json directly", text)
        self.assertIn("non-empty actor_id", text)
        self.assertIn("automation-registry.json", text)
        self.assertIn("fail closed", text)

    def test_unknown_lane_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown chat lane"):
            bootstrap.build_prompt("does-not-exist", ROOT)


if __name__ == "__main__":
    unittest.main()
