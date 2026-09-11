from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import validate_history  # noqa: E402


class ValidateHistoryTest(unittest.TestCase):
    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def make_tree(self, root: Path) -> Path:
        manifest = root / "modules" / "network.http_client" / "1.0.0" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}\n", encoding="utf-8")
        self.write_json(
            root / "catalog" / "index.json",
            {
                "schema_version": 1,
                "library_id": "test",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-12T00:00:00Z",
                "assets": [
                    {
                        "id": "network.http_client",
                        "version": "1.0.0",
                        "manifest": "modules/network.http_client/1.0.0/manifest.json",
                        "status": "certified",
                        "capabilities": ["network.http"],
                    }
                ],
            },
        )
        return root / "observations" / "network.http_client" / "1.0.0.json"

    def test_valid_history_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history = self.make_tree(root)
            self.write_json(
                history,
                {
                    "schema_version": 1,
                    "asset_id": "network.http_client",
                    "version": "1.0.0",
                    "revision": 1,
                    "updated_at": "2026-09-12T00:01:00Z",
                    "events": [
                        {
                            "event_id": "event-1",
                            "type": "integration",
                            "occurred_at": "2026-09-12T00:00:00Z",
                            "source": "cantiere",
                            "outcome": "success",
                        }
                    ],
                },
            )
            previous = validate_history.ROOT
            validate_history.ROOT = root
            try:
                registered = validate_history.catalog_keys()
                validate_history.validate_history_file(history, registered)
            finally:
                validate_history.ROOT = previous

    def test_duplicate_event_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history = self.make_tree(root)
            event = {
                "event_id": "same-event",
                "type": "integration",
                "occurred_at": "2026-09-12T00:00:00Z",
                "source": "cantiere",
                "outcome": "success",
            }
            self.write_json(
                history,
                {
                    "schema_version": 1,
                    "asset_id": "network.http_client",
                    "version": "1.0.0",
                    "revision": 2,
                    "updated_at": "2026-09-12T00:01:00Z",
                    "events": [event, dict(event)],
                },
            )
            previous = validate_history.ROOT
            validate_history.ROOT = root
            try:
                with self.assertRaisesRegex(validate_history.ValidationError, "duplicate event_id"):
                    validate_history.validate_history_file(history, validate_history.catalog_keys())
            finally:
                validate_history.ROOT = previous

    def test_orphan_history_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history = self.make_tree(root)
            self.write_json(root / "catalog" / "index.json", {
                "schema_version": 1,
                "library_id": "test",
                "catalog_version": "1.0.0",
                "updated_at": "2026-09-12T00:00:00Z",
                "assets": [],
            })
            self.write_json(
                history,
                {
                    "schema_version": 1,
                    "asset_id": "network.http_client",
                    "version": "1.0.0",
                    "revision": 0,
                    "updated_at": None,
                    "events": [],
                },
            )
            previous = validate_history.ROOT
            validate_history.ROOT = root
            try:
                with self.assertRaisesRegex(validate_history.ValidationError, "non-catalogued"):
                    validate_history.validate_history_file(history, validate_history.catalog_keys())
            finally:
                validate_history.ROOT = previous


if __name__ == "__main__":
    unittest.main()
