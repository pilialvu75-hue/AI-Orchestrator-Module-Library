"""Replay reservation is atomic and rejects duplicates in one ledger."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_reviewer_nonce_ledger import reserve_nonce


class NonceLedgerTests(unittest.TestCase):
    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = dict(reviewer_key_id="reviewer", nonce="n-1", ledger_dir=directory)
            self.assertTrue(reserve_nonce(**args))
            self.assertFalse(reserve_nonce(**args))
            self.assertTrue(reserve_nonce(**dict(args, nonce="n-2")))

    def test_concurrent_reservation_has_one_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            args = dict(reviewer_key_id="reviewer", nonce="shared", ledger_dir=directory)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: reserve_nonce(**args), range(16)))
            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), 15)

    def test_missing_ledger_and_invalid_nonce_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                reserve_nonce(reviewer_key_id="reviewer", nonce="x",
                              ledger_dir=str(Path(directory) / "missing"))
            with self.assertRaises(ValueError):
                reserve_nonce(reviewer_key_id="reviewer", nonce="",
                              ledger_dir=directory)


if __name__ == "__main__":
    unittest.main()
