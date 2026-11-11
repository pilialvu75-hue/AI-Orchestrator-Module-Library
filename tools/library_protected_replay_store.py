"""Protected replay-store contract for cross-run reviewer attestations.

A production implementation MUST provide an atomic, durable insert-if-absent
transaction shared by all reviewer jobs. This module has no default backend:
local files, Actions artifacts, caches and issue comments are not suitable.
"""
import hashlib


def consume_protected_nonce(store, *, reviewer_key_id, nonce):
    if not isinstance(reviewer_key_id, str) or not reviewer_key_id:
        raise ValueError("reviewer identity required")
    if not isinstance(nonce, str) or not nonce:
        raise ValueError("nonce required")
    if store is None or not callable(getattr(store, "insert_if_absent", None)):
        raise ValueError("protected transactional replay store required")
    identity = hashlib.sha256((reviewer_key_id + "\0" + nonce).encode("utf-8")).hexdigest()
    # Backend must guarantee exactly one winner across jobs/runners. Exceptions
    # propagate and fail closed; a timeout must NEVER be treated as success.
    result = store.insert_if_absent(identity)
    if type(result) is not bool:
        raise ValueError("replay store must return an explicit boolean")
    return result
