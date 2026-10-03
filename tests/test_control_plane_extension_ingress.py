import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "control_plane_extension_ingress",
    ROOT / "tools" / "control_plane_extension_ingress.py",
)
ingress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingress)


class ExtensionIngressGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / ".airlab", self.root / ".airlab")
        self.pending = self.root / ".airlab/control-plane/inbox/pending"
        self.pending.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name, request):
        path = self.pending / f"{name}.json"
        path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        return path

    def test_malformed_wait_request_is_quarantined_before_specialized_processor(self):
        path = self._write("bad-wait", {
            "schema_version": 1,
            "request_id": "bad-wait",
            "actor_id": "chatgpt:cantiere",
            "lane_id": "cantiere",
            "operation": "enter_wait",
            "expected_state_version": "wrong-type",
            "payload": {},
        })
        outcomes = ingress.guard(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 40, tzinfo=timezone.utc),
        )
        self.assertTrue(any("bad-wait" in item and "quarantined" in item for item in outcomes))
        self.assertFalse(path.exists())
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/quarantine/bad-wait.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["status"], "QUARANTINED")
        self.assertIn("expected_state_version", receipt["errors"][0])

    def test_non_reviewer_stale_resolution_is_quarantined(self):
        path = self._write("bad-reviewer", {
            "schema_version": 1,
            "request_id": "bad-reviewer",
            "actor_id": "automation:main-reviewer",
            "lane_id": "main-reviewer",
            "operation": "resolve_stale_block",
            "expected_state_version": 41,
            "payload": {},
        })
        outcomes = ingress.guard(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 40, tzinfo=timezone.utc),
        )
        self.assertTrue(any("bad-reviewer" in item and "quarantined" in item for item in outcomes))
        self.assertFalse(path.exists())
        receipt = json.loads(
            (self.root / ".airlab/control-plane/inbox/quarantine/bad-reviewer.json").read_text(encoding="utf-8")
        )
        self.assertIn("restricted to chatgpt:main-reviewer", receipt["errors"][0])

    def test_valid_wait_request_is_left_for_wait_processor(self):
        path = self._write("good-wait", {
            "schema_version": 1,
            "request_id": "good-wait",
            "actor_id": "chatgpt:cantiere",
            "lane_id": "cantiere",
            "operation": "resume_wait",
            "expected_state_version": 12,
            "payload": {"signal_id": "device-result", "evidence_refs": ["run:1"]},
        })
        outcomes = ingress.guard(
            root=self.root,
            now=datetime(2026, 10, 3, 16, 40, tzinfo=timezone.utc),
        )
        self.assertEqual(outcomes, [])
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
