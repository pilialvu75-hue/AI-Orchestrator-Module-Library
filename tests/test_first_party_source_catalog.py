from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / ".airlab" / "first-party-sources.json"
REPOSITORY = re.compile(r"^pilialvu75-hue/[A-Za-z0-9._-]+$")
CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9._-]+$")
FORBIDDEN = {".env", ".git", "node_modules", "build"}
FORBIDDEN_SUFFIXES = (".jks", ".keystore", ".p12", ".pfx", ".pem", ".key")


class FirstPartySourceCatalogTest(unittest.TestCase):
    def test_catalog_is_read_only_and_bounded(self) -> None:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        policy = data["policy"]
        self.assertEqual(policy["access"], "read_only")
        self.assertFalse(policy["execute_source"])
        self.assertFalse(policy["fetch_arbitrary_file_contents"])
        self.assertEqual(policy["submit_destination"], "library_intake_only")
        self.assertTrue(policy["certification_required"])

        seen = set()
        for source in data["sources"]:
            repository = source["repository"]
            self.assertRegex(repository, REPOSITORY)
            self.assertNotIn(repository, seen)
            seen.add(repository)
            for candidate in source.get("candidates", []):
                self.assertRegex(candidate["capability_id"], CAPABILITY)
                path = candidate["component_path"]
                self.assertFalse(path.startswith(("/", "~")))
                self.assertNotIn("\\", path)
                parts = [part.lower() for part in path.split("/")]
                self.assertTrue(all(part not in {"", ".", ".."} for part in parts))
                self.assertTrue(all(part not in FORBIDDEN for part in parts))
                self.assertFalse(parts[-1].endswith(FORBIDDEN_SUFFIXES))


if __name__ == "__main__":
    unittest.main()
