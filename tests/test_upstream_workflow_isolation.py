from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "certify-upstream-intakes.yml"
CANTIERE_BUILD = ROOT / ".github" / "workflows" / "build-cantiere-android.yml"


class UpstreamWorkflowIsolationTest(unittest.TestCase):
    def test_untrusted_execution_has_no_library_write_permission(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("validate_untrusted:", text)
        self.assertIn("promote_trusted:", text)

        prefix, trusted = text.split("  promote_trusted:", 1)
        untrusted = prefix.split("  validate_untrusted:", 1)[1]

        self.assertNotIn("contents: write", prefix)
        self.assertIn("permissions: {}", untrusted)
        self.assertIn("dart analyze --fatal-infos", untrusted)
        self.assertIn("dart test", untrusted)
        self.assertNotIn("actions/checkout@", untrusted)

        self.assertIn("contents: write", trusted)
        self.assertIn("actions/checkout@v6", trusted)
        self.assertIn("persist-credentials: false", prefix)
        self.assertIn("actions/upload-artifact@v6", untrusted)
        self.assertIn("actions/download-artifact@v6", trusted)

        # Upstream code execution must exist only before the trusted writer job.
        self.assertNotRegex(trusted, re.compile(r"\bdart\s+test\b"))
        self.assertNotRegex(trusted, re.compile(r"\bdart\s+analyze\b"))
        self.assertNotIn("flutter pub get", trusted)

    def test_private_source_staging_dependency_is_acyclic(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        staging = text.split("  stage_trusted_source:", 1)[1].split("  validate_untrusted:", 1)[0]
        validation = text.split("  validate_untrusted:", 1)[1].split("  promote_trusted:", 1)[0]

        self.assertIn("needs: prepare", staging)
        self.assertNotIn("needs: [prepare, stage_trusted_source]", staging)
        self.assertIn("needs: [prepare, stage_trusted_source]", validation)

    def test_cantiere_build_does_not_keep_checkout_credentials(self) -> None:
        text = CANTIERE_BUILD.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("sparse-checkout:", text)
        self.assertIn(".cantiere-build/source", text)
        self.assertIn("sparse-checkout-cone-mode: false", text)
        self.assertNotIn("contents: write", text)
        setup_java, _ = text.split("      - name: Setup Flutter", 1)
        setup_java = setup_java.split("      - name: Setup Java", 1)[1]
        self.assertNotIn("cache: gradle", setup_java)
        self.assertIn(
            "Do not enable setup-java's Gradle cache here",
            setup_java,
        )


if __name__ == "__main__":
    unittest.main()
