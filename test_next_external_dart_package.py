import unittest
from tools.select_next_external_dart_package import select


class NextCandidateTest(unittest.TestCase):
    def test_skips_admitted_and_pilots(self):
        discovery = {"source_commit": "a" * 40, "candidates": [
            {"package": "args", "state": "DISCOVERED_UNTESTED"},
            {"package": "characters", "state": "DISCOVERED_UNTESTED"},
            {"package": "async", "state": "DISCOVERED_UNTESTED"}]}
        manifests = [{"provenance": {"source_subtree": "pkgs/args"}}]
        result = select(discovery, manifests)
        self.assertEqual(result["package"], "async")
        self.assertEqual(result["status"], "DISCOVERED_UNTESTED")
        self.assertFalse(result["certification_authorized"])

    def test_rejects_no_candidate(self):
        with self.assertRaises(ValueError):
            select({"source_commit": "a" * 40, "candidates": [
                {"package": "args", "state": "DISCOVERED_UNTESTED"}]},
                [{"provenance": {"source_subtree": "pkgs/args"}}])


if __name__ == "__main__":
    unittest.main()
