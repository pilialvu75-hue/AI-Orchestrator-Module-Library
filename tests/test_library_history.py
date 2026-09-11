from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_history import (  # noqa: E402
    AssetRef,
    HistoryError,
    compare_semver,
    compare_versions,
    record_event,
    summary,
)


class LibraryHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "catalog").mkdir(parents=True)
        self.assets = [
            {
                "id": "voice.stt_engine",
                "version": "1.9.0",
                "manifest": "modules/voice.stt_engine/1.9.0/manifest.json",
                "status": "certified",
                "capabilities": ["voice.stt"],
                "platforms": ["android"],
                "contracts": ["voice.stt.v1"],
            },
            {
                "id": "voice.stt_engine",
                "version": "1.10.0",
                "manifest": "modules/voice.stt_engine/1.10.0/manifest.json",
                "status": "certified",
                "capabilities": ["voice.stt"],
                "platforms": ["android", "linux"],
                "contracts": ["voice.stt.v1"],
            },
        ]
        (self.root / "catalog" / "index.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "library_id": "test",
                    "catalog_version": "1.0.0",
                    "updated_at": "2026-09-12T00:00:00Z",
                    "assets": self.assets,
                }
            ),
            encoding="utf-8",
        )
        for item in self.assets:
            path = self.root / item["manifest"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def event(event_id: str, *, outcome: str = "success", target: str = "android") -> dict:
        return {
            "event_id": event_id,
            "type": "integration",
            "occurred_at": "2026-09-12T00:00:00Z",
            "source": "cantiere",
            "outcome": outcome,
            "target": target,
            "contract_id": "voice.stt.v1",
            "project_id": "project-a",
            "score": None,
            "notes": None,
            "metadata": {},
        }

    def test_record_is_idempotent_by_event_id_and_content(self) -> None:
        ref = AssetRef("voice.stt_engine", "1.10.0")
        first = record_event(self.root, ref, self.event("integration-1"))
        self.assertEqual("recorded", first["result"])
        self.assertEqual(1, first["revision"])

        again = record_event(self.root, ref, self.event("integration-1"))
        self.assertEqual("already_recorded", again["result"])
        self.assertEqual(1, again["revision"])

        with self.assertRaisesRegex(HistoryError, "different content"):
            record_event(self.root, ref, self.event("integration-1", outcome="failure"))

    def test_summary_keeps_runtime_quality_outside_immutable_manifest(self) -> None:
        ref = AssetRef("voice.stt_engine", "1.10.0")
        record_event(self.root, ref, self.event("integration-1", outcome="success"))
        record_event(self.root, ref, self.event("integration-2", outcome="failure"))

        data = summary(self.root, ref)
        observations = data["observations"]
        self.assertEqual(2, observations["reuse_count"])
        self.assertEqual(1, observations["successful_integrations"])
        self.assertEqual(1, observations["failed_integrations"])
        self.assertEqual(0.5, observations["success_rate"])

    def test_compare_versions_uses_semver_not_lexical_order(self) -> None:
        data = compare_versions(self.root, "voice.stt_engine")
        self.assertEqual(["1.9.0", "1.10.0"], [item["version"] for item in data["versions"]])
        self.assertEqual("1.10.0", data["latest_version"])

    def test_semver_orders_prerelease_before_stable(self) -> None:
        self.assertLess(compare_semver("2.0.0-rc.1", "2.0.0"), 0)
        self.assertLess(compare_semver("2.0.0-rc.2", "2.0.0-rc.10"), 0)

    def test_unknown_version_cannot_receive_history(self) -> None:
        with self.assertRaisesRegex(HistoryError, "not registered"):
            record_event(
                self.root,
                AssetRef("voice.stt_engine", "9.9.9"),
                self.event("integration-unknown"),
            )


if __name__ == "__main__":
    unittest.main()
