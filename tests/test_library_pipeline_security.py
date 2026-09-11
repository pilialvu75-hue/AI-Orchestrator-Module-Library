from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from library_pipeline import (  # noqa: E402
    AssetRef,
    PipelineError,
    license_requires_explicit_review,
    validate_no_symlinks,
    validate_ref,
)


class LibraryPipelineSecurityTest(unittest.TestCase):
    def test_asset_id_rejects_path_traversal(self) -> None:
        with self.assertRaisesRegex(PipelineError, "path separators"):
            validate_ref(AssetRef("../escape", "1.0.0"))

    def test_license_detection_does_not_confuse_lgpl_with_gpl(self) -> None:
        self.assertTrue(license_requires_explicit_review("GPL-3.0-only"))
        self.assertTrue(license_requires_explicit_review("AGPL-3.0-only"))
        self.assertTrue(license_requires_explicit_review("SSPL-1.0"))
        self.assertFalse(license_requires_explicit_review("LGPL-3.0-only"))
        self.assertFalse(license_requires_explicit_review("MIT"))

    def test_untrusted_intake_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = root / "asset"
            asset.mkdir()
            outside = root / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            (asset / "link.txt").symlink_to(outside)

            with self.assertRaisesRegex(PipelineError, "symlinks are not allowed"):
                validate_no_symlinks(asset)


if __name__ == "__main__":
    unittest.main()
