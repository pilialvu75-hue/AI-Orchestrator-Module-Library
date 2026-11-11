"""Persistent SQLite replay protection across independent connections."""
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_protected_replay_store import consume_protected_nonce
from library_sqlite_replay_store import SQLiteReplayStore


class SQLiteReplayTests(unittest.TestCase):
    def test_reopen_does_not_reuse_nonce(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "replay.sqlite"
            first = SQLiteReplayStore(path)
            self.assertTrue(consume_protected_nonce(first, reviewer_key_id="reviewer", nonce="one"))
            second = SQLiteReplayStore(path)
            self.assertFalse(consume_protected_nonce(second, reviewer_key_id="reviewer", nonce="one"))
            self.assertTrue(consume_protected_nonce(second, reviewer_key_id="reviewer", nonce="two"))

    def test_parallel_connections_only_one_winner(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "replay.sqlite"
            SQLiteReplayStore(path)
            def consume(_):
                return consume_protected_nonce(SQLiteReplayStore(path),
                                               reviewer_key_id="reviewer", nonce="shared")
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(consume, range(20)))
            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), 19)

    def test_symlink_database_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.sqlite"
            SQLiteReplayStore(target)
            (root / "link.sqlite").symlink_to(target)
            with self.assertRaises(ValueError):
                SQLiteReplayStore(root / "link.sqlite")

    def test_broad_permissions_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "replay.sqlite"
            SQLiteReplayStore(path)
            os.chmod(path, 0o644)
            with self.assertRaises(ValueError):
                SQLiteReplayStore(path)

    def test_missing_parent_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                SQLiteReplayStore(Path(temp) / "missing" / "db.sqlite")


if __name__ == "__main__":
    unittest.main()
