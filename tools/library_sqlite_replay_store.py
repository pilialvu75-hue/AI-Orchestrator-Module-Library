"""SQLite transactional replay store for a protected, persistent volume.

Use only on a trusted shared filesystem with correct SQLite locking. A
GitHub-hosted runner's local disk is ephemeral and NOT cross-run protection.
"""
import sqlite3
from pathlib import Path


class SQLiteReplayStore:
    def __init__(self, database_path):
        path = Path(database_path)
        if not path.parent.is_dir() or path.is_symlink():
            raise ValueError("protected persistent database directory required")
        self.path = str(path)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS consumed_nonces "
                         "(identity TEXT PRIMARY KEY NOT NULL)")

    def insert_if_absent(self, identity):
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("invalid nonce digest")
        with sqlite3.connect(self.path, timeout=10, isolation_level=None) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = conn.execute(
                    "INSERT OR IGNORE INTO consumed_nonces(identity) VALUES (?)",
                    (identity,))
                inserted = result.rowcount == 1
                conn.execute("COMMIT")
                return inserted
            except BaseException:
                conn.execute("ROLLBACK")
                raise
