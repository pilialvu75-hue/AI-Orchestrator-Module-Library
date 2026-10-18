"""Guardrails for race-safe, allowlisted Library inventory writes."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/library-firstparty-quarantine.yml"


class ReadinessWorkflowRaceTests(unittest.TestCase):
    def test_retries_recompute_against_current_main_before_each_push(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text.split("for attempt in 1 2 3; do", 1)[1].split(
            "done\n          echo \"Readiness reconciliation exhausted", 1
        )[0]
        self.assertLess(section.index("git fetch origin main"),
                        section.index("git reset --hard origin/main"))
        self.assertLess(section.index("git reset --hard origin/main"),
                        section.index("python -m tools.library_firstparty_quarantine --apply"))
        self.assertLess(section.index("python -m tools.library_firstparty_quarantine --apply"),
                        section.index("python -m tools.library_intake_readiness --output"))
        self.assertLess(section.index("python -m tools.library_intake_readiness --output"),
                        section.index("python tools/validate_library.py"))
        self.assertLess(section.index("python tools/validate_library.py"),
                        section.index("python -m unittest discover"))
        self.assertLess(section.index("python -m unittest discover"),
                        section.index("git add -- catalog/intake-readiness.json"))
        self.assertLess(section.index("git add -- catalog/intake-readiness.json"),
                        section.index("if git push origin HEAD:main; then"))
        self.assertNotIn("git push --force", text)
        self.assertNotIn("git push -f", text)
        self.assertIn("Readiness reconciliation exhausted three compare-and-swap retries", text)

    def test_workflow_never_stages_module_certification_from_readiness(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("catalog/intake-readiness.json)", text)
        self.assertIn('git add -- catalog/intake-readiness.json', text)
        self.assertNotIn("git add -- modules", text)
        self.assertNotIn("git add -A", text)
        self.assertNotIn("git add .", text)
        self.assertNotIn("autonomous_finalize_needs", text)


if __name__ == "__main__":
    unittest.main()
