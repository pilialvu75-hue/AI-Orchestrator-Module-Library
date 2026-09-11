from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_lifecycle import LifecycleError, apply_transition, rollback_plan  # noqa: E402


class LibraryLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "catalog").mkdir(parents=True)
        assets = []
        for version in ("1.0.0", "1.1.0", "2.0.0"):
            assets.append(
                {
                    "id": "voice.stt_engine",
                    "version": version,
                    "manifest": f"modules/voice.stt_engine/{version}/manifest.json",
                    "status": "certified",
                    "kind": "integration_bundle",
                    "capabilities": ["voice.stt"],
                    "platforms": ["android"],
                    "contracts": ["voice.stt.v1"],
                }
            )
        self.write_json(
            self.root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "test",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-12T00:00:00Z",
                "assets": assets,
            },
        )
        self.write_json(
            self.root / "catalog" / "lifecycle.json",
            {"schema_version": 1, "revision": 0, "updated_at": None, "events": []},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_deprecate_and_reinstate_are_audited(self) -> None:
        result = apply_transition(
            self.root,
            asset_id="voice.stt_engine",
            version="1.1.0",
            target="deprecated",
            reason="Superseded for new projects",
            source="library",
            event_id="dep-1",
            occurred_at="2026-09-12T01:00:00Z",
        )
        self.assertEqual("transitioned", result["result"])

        catalog = json.loads((self.root / "catalog" / "index.json").read_text())
        item = next(asset for asset in catalog["assets"] if asset["version"] == "1.1.0")
        self.assertEqual("deprecated", item["availability"])

        restored = apply_transition(
            self.root,
            asset_id="voice.stt_engine",
            version="1.1.0",
            target="active",
            reason="Regression in successor made this preferred again",
            source="library",
            event_id="reinstate-1",
            occurred_at="2026-09-12T02:00:00Z",
        )
        self.assertEqual("transitioned", restored["result"])
        ledger = json.loads((self.root / "catalog" / "lifecycle.json").read_text())
        self.assertEqual(2, ledger["revision"])
        self.assertEqual(["deprecated", "active"], [event["to"] for event in ledger["events"]])

    def test_revoked_version_cannot_be_reinstated_by_normal_command(self) -> None:
        apply_transition(
            self.root,
            asset_id="voice.stt_engine",
            version="1.1.0",
            target="revoked",
            reason="Critical security issue",
            source="security",
            event_id="revoke-1",
            occurred_at="2026-09-12T01:00:00Z",
        )
        with self.assertRaisesRegex(LifecycleError, "forbidden"):
            apply_transition(
                self.root,
                asset_id="voice.stt_engine",
                version="1.1.0",
                target="active",
                reason="Unsafe manual restore",
                source="manual",
            )

    def test_rollback_prefers_highest_lower_active_semver(self) -> None:
        plan = rollback_plan(
            self.root,
            asset_id="voice.stt_engine",
            from_version="2.0.0",
            target="android",
            contract_id="voice.stt.v1",
        )
        self.assertEqual("1.1.0", plan["recommended"]["version"])
        self.assertFalse(plan["automatic_switch_performed"])

    def test_rollback_excludes_deprecated_unless_explicitly_requested(self) -> None:
        apply_transition(
            self.root,
            asset_id="voice.stt_engine",
            version="1.1.0",
            target="deprecated",
            reason="Known issue on some devices",
            source="library",
            event_id="dep-rollback",
            occurred_at="2026-09-12T01:00:00Z",
        )
        safe = rollback_plan(self.root, asset_id="voice.stt_engine", from_version="2.0.0")
        self.assertEqual("1.0.0", safe["recommended"]["version"])

        expanded = rollback_plan(
            self.root,
            asset_id="voice.stt_engine",
            from_version="2.0.0",
            include_deprecated=True,
        )
        self.assertEqual("1.1.0", expanded["recommended"]["version"])

    def test_replacement_must_exist_and_not_be_revoked(self) -> None:
        apply_transition(
            self.root,
            asset_id="voice.stt_engine",
            version="1.1.0",
            target="revoked",
            reason="Critical issue",
            source="security",
            event_id="revoked-replacement",
            occurred_at="2026-09-12T01:00:00Z",
        )
        with self.assertRaisesRegex(LifecycleError, "replacement cannot be revoked"):
            apply_transition(
                self.root,
                asset_id="voice.stt_engine",
                version="2.0.0",
                target="deprecated",
                reason="Use older branch",
                source="library",
                replacement_text="voice.stt_engine@1.1.0",
            )


if __name__ == "__main__":
    unittest.main()
