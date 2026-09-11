from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import validate_lifecycle  # noqa: E402
from library_lifecycle import apply_transition  # noqa: E402


class ValidateLifecycleTest(unittest.TestCase):
    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def make_tree(self, root: Path) -> None:
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
                        "platforms": ["android"],
                        "contracts": ["network.http.v1"]
                    }
                ]
            }
        )
        self.write_json(
            root / "catalog" / "lifecycle.json",
            {"schema_version": 1, "revision": 0, "updated_at": None, "events": []}
        )

    def run_validator(self, root: Path) -> int:
        previous = validate_lifecycle.ROOT
        validate_lifecycle.ROOT = root
        try:
            return validate_lifecycle.main()
        finally:
            validate_lifecycle.ROOT = previous

    def test_tool_transition_produces_valid_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root)
            apply_transition(
                root,
                asset_id="network.http_client",
                version="1.0.0",
                target="deprecated",
                reason="A newer implementation is preferred",
                source="library",
                event_id="dep-http-1",
                occurred_at="2026-09-12T01:00:00Z",
            )
            self.assertEqual(0, self.run_validator(root))

    def test_catalog_state_without_matching_ledger_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root)
            catalog_path = root / "catalog" / "index.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog["assets"][0]["availability"] = "revoked"
            self.write_json(catalog_path, catalog)
            self.assertEqual(1, self.run_validator(root))


if __name__ == "__main__":
    unittest.main()
