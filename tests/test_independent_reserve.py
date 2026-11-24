import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_resolver import select_independent_pair


def asset(id, origin, digest, status="certified", availability="active"):
    return dict(id=id, provenance=dict(source_repository=origin),
                payload=dict(sha256=digest), status=status, availability=availability)


class ReserveTests(unittest.TestCase):
    def test_distinct_implementation(self):
        primary = asset("a", "https://github.com/a/a", "one")
        rows = [primary, asset("a", "other", "two"),
                asset("b", "https://github.com/A/A/", "three"),
                asset("c", "third", "one"),
                asset("d", "fourth", "four", status="tested"),
                asset("e", "fifth", "five", availability="deprecated"),
                asset("f", "sixth", "six")]
        result = select_independent_pair(rows)
        self.assertEqual(result["primary"], primary)
        self.assertEqual(result["reserve"]["id"], "f")
        self.assertFalse(result["reserve_missing"])

    def test_missing_reserve(self):
        result = select_independent_pair([asset("a", "origin", "one")])
        self.assertIsNone(result["reserve"])
        self.assertTrue(result["reserve_missing"])

    def test_empty(self):
        self.assertIsNone(select_independent_pair([])["primary"])

    def test_unknown_provenance(self):
        rows = [asset("a", None, "one"), asset("b", "origin", "two")]
        self.assertTrue(select_independent_pair(rows)["reserve_missing"])


if __name__ == "__main__":
    unittest.main()
