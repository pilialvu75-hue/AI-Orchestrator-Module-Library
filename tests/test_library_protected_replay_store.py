"""Contract tests for an externally protected replay store."""
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_protected_replay_store import consume_protected_nonce


class AtomicStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.seen = set()

    def insert_if_absent(self, key):
        with self.lock:
            if key in self.seen:
                return False
            self.seen.add(key)
            return True


class ProtectedReplayTests(unittest.TestCase):
    def test_missing_store_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "protected transactional"):
            consume_protected_nonce(None, reviewer_key_id="reviewer", nonce="one")

    def test_atomic_store_rejects_replay(self):
        store = AtomicStore()
        args = dict(store=store, reviewer_key_id="reviewer", nonce="one")
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: consume_protected_nonce(**args), range(20)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 19)

    def test_backend_failure_is_not_approval(self):
        class Broken:
            def insert_if_absent(self, key):
                raise TimeoutError("store unreachable")
        with self.assertRaises(TimeoutError):
            consume_protected_nonce(Broken(), reviewer_key_id="reviewer", nonce="one")

    def test_backend_must_return_boolean(self):
        class Ambiguous:
            def insert_if_absent(self, key):
                return None
        with self.assertRaisesRegex(ValueError, "explicit boolean"):
            consume_protected_nonce(Ambiguous(), reviewer_key_id="reviewer", nonce="one")


if __name__ == "__main__":
    unittest.main()
