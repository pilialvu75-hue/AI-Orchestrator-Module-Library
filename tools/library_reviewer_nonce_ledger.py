"""Local atomic replay guard for verified reviewer attestations.

This is only a single-filesystem primitive. A production reviewer must use a
protected shared transactional store across jobs/runners; no certification is
authorized by this module.
"""
import hashlib
import os
from pathlib import Path


def reserve_nonce(*, reviewer_key_id, nonce, ledger_dir):
    if not isinstance(reviewer_key_id, str) or not reviewer_key_id or not isinstance(nonce, str) or not nonce:
        raise ValueError("invalid reviewer identity or nonce")
    directory = Path(ledger_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("protected replay ledger directory must already exist")
    identity = (reviewer_key_id + "\0" + nonce).encode("utf-8")
    filename = hashlib.sha256(identity).hexdigest() + ".used"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(directory / filename, flags, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as stream:
        stream.write(hashlib.sha256(identity).hexdigest().encode("ascii") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True
