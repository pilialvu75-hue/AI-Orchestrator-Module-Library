"""Transactional SQLite replay ledger concurrency regression tests."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_reviewer_shared_nonce_ledger import initialize_protected_database, reserve_shared_nonce


class SharedLedgerTests(unittest.TestCase):
    def test_only_one_transaction_can_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ledger.sqlite"
            initialize_protected_database(db)
            args = dict(reviewer_key_id="reviewer", nonce="nonce-1", database_path=db)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: reserve_shared_nonce(**args), range(16)))
            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), 15)
            self.assertTrue(reserve_shared_nonce(**dict(args, nonce="nonce-2")))

    def test_missing_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                reserve_shared_nonce(reviewer_key_id="r", nonce="n",
                                     database_path=Path(tmp) / "missing.sqlite")


if __name__ == "__main__":
    unittest.main()
