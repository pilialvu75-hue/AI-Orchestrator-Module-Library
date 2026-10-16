"""Negative and positive contract tests for the pure GitHub check verifier."""
import unittest

from tools.autonomous_ci_verifier import verify_pr_checks

SHA = "a" * 40
REPO = "owner/repo"


def inputs():
    return {
        "pr": {"number": 120, "state": "open", "head": {"sha": SHA, "repo": {"full_name": REPO}}},
        "checks": [
            {"name": "Validate Module Library", "head_sha": SHA,
             "status": "completed", "conclusion": "success",
             "app": {"slug": "github-actions"}, "id": 42}
        ],
        "repository": REPO,
        "expected_head_sha": SHA,
        "required_check_names": ["Validate Module Library"],
    }


class VerifierTests(unittest.TestCase):
    def test_valid_check_is_not_completion_authority(self):
        result = verify_pr_checks(**inputs())
        self.assertEqual(result["verified_checks"], {"Validate Module Library": 42})
        self.assertFalse(result["trusted_receipt"])
        self.assertFalse(result["completion_authorized"])

    def test_rejects_mismatches_and_missing_evidence(self):
        mutations = [
            lambda x: x["pr"]["head"].update(sha="b" * 40),
            lambda x: x["pr"]["head"]["repo"].update(full_name="other/repo"),
            lambda x: x["pr"].update(state="closed"),
            lambda x: x["pr"].pop("number"),
            lambda x: x["pr"].update(number=0),
            lambda x: x["pr"].update(number=True),
            lambda x: x["pr"].update(number="120"),
            lambda x: x["checks"][0].update(head_sha="b" * 40),
            lambda x: x["checks"][0].update(status="in_progress"),
            lambda x: x["checks"][0].update(conclusion="failure"),
            lambda x: x["checks"][0]["app"].update(slug="unknown"),
            lambda x: x["checks"].clear(),
            lambda x: x["checks"].append(dict(x["checks"][0])),
            lambda x: x.update(required_check_names=["Not Found"]),
            lambda x: x.update(required_check_names=["Validate Module Library"] * 2),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                data = inputs()
                mutation(data)
                with self.assertRaises(ValueError):
                    verify_pr_checks(**data)


if __name__ == "__main__":
    unittest.main()
