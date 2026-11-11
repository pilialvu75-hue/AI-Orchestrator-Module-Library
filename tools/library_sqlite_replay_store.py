"""SQLite transactional replay store for a protected, persistent volume.

Use only on a trusted shared filesystem with correct SQLite locking. A
GitHub-hosted runner's local disk is ephemeral and NOT cross-run protection.
"""
import os
import stat
import sqlite3
from pathlib import Path


class SQLiteReplayStore:
    def __init__(self, database_path):
        path = Path(database_path)
        if not path.parent.is_dir() or path.parent.is_symlink() or path.is_symlink():
            raise ValueError("protected persistent database directory required")
        if path.exists() and not path.is_file():
            raise ValueError("replay database must be a regular file")
        if path.exists() and (path.stat().st_mode & 0o077):
            raise ValueError("replay database must not be accessible to group or others")
        self.path = str(path)
        # Restrictive creation permissions; parent directory must be owned and
        # protected by the reviewer service, not writable by candidate code.
        previous_umask = os.umask(0o077)
        try:
            with sqlite3.connect(self.path, timeout=10) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS consumed_nonces "
                             "(identity TEXT PRIMARY KEY NOT NULL)")
        finally:
            os.umask(previous_umask)
        if os.stat(self.path).st_mode & 0o077:
            raise ValueError("replay database permissions are too broad")
        # Existing files are not trusted unless protected by filesystem ACLs.

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
