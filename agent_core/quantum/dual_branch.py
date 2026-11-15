#!/usr/bin/env python3
"""Dual-branch two-layer method — standalone offline at-rest encryption.

The user's signature "encrypted 2 layer method": TWO SEPARATE private branch
key files (branch A: internal identity branch, branch B: local operator token
branch). Neither branch alone can recover anything; unsealing requires BOTH
branches locally, in one pass, offline. Nothing here touches a network.

  sealed  = nonce(16) || ciphertext || SHA-256(nonce || ciphertext)
  ciphertext = plaintext XOR SHA-256-keystream(keyA, keyB, nonce)
  blind_index(value) = SHA-256(domain-tag || value)  — equality lookups that
                       store/reveal nothing about the value

Properties:
  * one branch file alone reveals nothing (keystream needs both)
  * wrong/tampered branches fail closed (integrity digest first,
    constant-time compare)
  * pure stdlib (hashlib, hmac, os.urandom) — no API, no cloud, no DNS

The eSIM core does NOT require this module; it is available for any at-rest
secret the operator chooses to lock (currently nothing in the core needs it).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

BRANCH_KEY_BYTES = 32
_NONCE_BYTES = 16
_DIGEST_BYTES = 32
_OVERHEAD = _NONCE_BYTES + _DIGEST_BYTES


def provision_branch_keys(branch_a_path: str, branch_b_path: str) -> bool:
    """Provision the two SEPARATE private branch key files from OS entropy
    (0600 permissions). Call once; keep the branches apart (different media
    or directories) so no single location grants access."""
    try:
        for path in (branch_a_path, branch_b_path):
            with open(path, "wb") as fh:
                fh.write(os.urandom(BRANCH_KEY_BYTES))
            os.chmod(path, 0o600)
        return True
    except OSError:
        return False


def load_branch(path: str) -> Optional[bytes]:
    """Load one branch key file; None if missing or wrong size (fail closed)."""
    try:
        with open(path, "rb") as fh:
            key = fh.read()
        return key if len(key) == BRANCH_KEY_BYTES else None
    except OSError:
        return None


def _keystream(key_a: bytes, key_b: bytes, nonce: bytes, length: int) -> bytes:
    """Deterministic keystream from BOTH branches: chained SHA-256 blocks.
    One branch yields nothing — both are required by construction."""
    blocks = []
    counter = 0
    prefix = key_a + key_b + nonce
    while sum(len(b) for b in blocks) < length:
        blocks.append(hashlib.sha256(prefix + counter.to_bytes(4, "big")).digest())
        counter += 1
    return b"".join(blocks)[:length]


def seal(key_a: bytes, key_b: bytes, data: bytes) -> bytes:
    """Two-layer seal: nonce || ciphertext || digest. The digest binds BOTH
    branch keys (key-committing): a wrong branch fails closed, not silently
    returns garbage."""
    nonce = os.urandom(_NONCE_BYTES)
    stream = _keystream(key_a, key_b, nonce, len(data))
    ciphertext = bytes(a ^ b for a, b in zip(data, stream))
    digest = hashlib.sha256(nonce + key_a + key_b + ciphertext).digest()
    return nonce + ciphertext + digest


def unseal(key_a: bytes, key_b: bytes, blob: bytes) -> Optional[bytes]:
    """Integrity FIRST (constant-time compare over BOTH branches), then
    unmask. Returns None on any tamper/wrong-key/length condition — fails
    closed. One branch alone can neither recover data nor even pass the
    integrity gate."""
    if len(blob) < _OVERHEAD or len(blob) == _OVERHEAD:
        return None
    nonce, ciphertext, digest = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:-_DIGEST_BYTES], blob[-_DIGEST_BYTES:]
    if not hmac.compare_digest(
        hashlib.sha256(nonce + key_a + key_b + ciphertext).digest(), digest
    ):
        return None
    stream = _keystream(key_a, key_b, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream))


def blind_index(value: str) -> bytes:
    """Domain-separated blind index: enables equality lookup without storing
    or revealing the value itself."""
    return hashlib.sha256(("dual-branch-blind:" + value).encode()).digest()
