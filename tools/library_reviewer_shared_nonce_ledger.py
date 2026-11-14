"""Transactional replay ledger for a protected shared SQLite database.

The caller MUST provide a durable database on a protected shared filesystem
or a single authoritative reviewer service. GitHub-hosted runner-local files
are NOT shared or durable; this module never authorizes certification.
"""
import hashlib
import sqlite3
from pathlib import Path


def reserve_shared_nonce(*, reviewer_key_id, nonce, database_path):
    if not isinstance(reviewer_key_id, str) or not reviewer_key_id or not isinstance(nonce, str) or not nonce:
        raise ValueError("invalid reviewer identity or nonce")
    db = Path(database_path)
    if not db.is_file() or db.is_symlink():
        raise ValueError("protected persistent replay database must already exist")
    digest = hashlib.sha256((reviewer_key_id + "\0" + nonce).encode("utf-8")).hexdigest()
    with sqlite3.connect(f"file:{db}?mode=rw", uri=True, timeout=20, isolation_level=None) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("INSERT INTO used_attestations (nonce_digest) VALUES (?)", (digest,))
            conn.execute("COMMIT")
            return True
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return False
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def initialize_protected_database(database_path):
    """Explicit operator setup; never invoked by an untrusted reviewer job."""
    db = Path(database_path)
    if db.exists():
        raise ValueError("refusing to overwrite existing replay database")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE used_attestations (nonce_digest TEXT PRIMARY KEY NOT NULL)")
