#!/usr/bin/env python3
"""Unit tests for the standalone dual-branch two-layer method (offline)."""

import os
import tempfile
import unittest

from dual_branch import (  # noqa: E402
    BRANCH_KEY_BYTES,
    blind_index,
    load_branch,
    provision_branch_keys,
    seal,
    unseal,
)


class TestProvisioning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = os.path.join(self.tmp.name, "branch_a.key")
        self.b = os.path.join(self.tmp.name, "branch_b.key")

    def tearDown(self):
        self.tmp.cleanup()

    def test_provision_creates_two_independent_keys(self):
        self.assertTrue(provision_branch_keys(self.a, self.b))
        ka, kb = load_branch(self.a), load_branch(self.b)
        self.assertEqual(len(ka), BRANCH_KEY_BYTES)
        self.assertEqual(len(kb), BRANCH_KEY_BYTES)
        self.assertNotEqual(ka, kb)

    def test_branch_files_are_0600(self):
        self.assertTrue(provision_branch_keys(self.a, self.b))
        for path in (self.a, self.b):
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_missing_branch_fails_closed(self):
        self.assertIsNone(load_branch(os.path.join(self.tmp.name, "nope.key")))


class TestSealUnseal(unittest.TestCase):
    def setUp(self):
        self.ka = b"A" * 32
        self.kb = b"B" * 32
        self.plaintext = b"sovereign-secret-payload"

    def test_roundtrip(self):
        blob = seal(self.ka, self.kb, self.plaintext)
        self.assertEqual(unseal(self.ka, self.kb, blob), self.plaintext)

    def test_ciphertext_differs_from_plaintext(self):
        blob = seal(self.ka, self.kb, self.plaintext)
        self.assertNotIn(self.plaintext, blob)

    def test_single_branch_reveals_nothing(self):
        blob = seal(self.ka, self.kb, self.plaintext)
        self.assertIsNone(unseal(self.ka, b"\x00" * 32, blob))
        self.assertIsNone(unseal(b"\x00" * 32, self.kb, blob))

    def test_wrong_branch_fails_closed(self):
        blob = seal(self.ka, self.kb, self.plaintext)
        self.assertIsNone(unseal(b"C" * 32, self.kb, blob))
        self.assertIsNone(unseal(self.ka, b"C" * 32, blob))

    def test_tamper_rejected(self):
        blob = seal(self.ka, self.kb, self.plaintext)
        for pos in (0, 16, len(blob) // 2, len(blob) - 1):
            tampered = bytearray(blob)
            tampered[pos] ^= 0x01
            self.assertIsNone(unseal(self.ka, self.kb, bytes(tampered)), f"pos={pos}")

    def test_empty_and_short_blobs_fail_closed(self):
        self.assertIsNone(unseal(self.ka, self.kb, b""))
        self.assertIsNone(unseal(self.ka, self.kb, b"\x00" * 48))
        self.assertIsNone(unseal(self.ka, self.kb, blob := b"\x00" * 10))

    def test_sealing_is_non_deterministic(self):
        """Same plaintext seals differently each time (fresh nonce) but both
        unseal to the same value."""
        b1 = seal(self.ka, self.kb, self.plaintext)
        b2 = seal(self.ka, self.kb, self.plaintext)
        self.assertNotEqual(b1, b2)
        self.assertEqual(unseal(self.ka, self.kb, b1), unseal(self.ka, self.kb, b2))

    def test_large_payload_roundtrip(self):
        big = os.urandom(10_000)
        blob = seal(self.ka, self.kb, big)
        self.assertEqual(unseal(self.ka, self.kb, blob), big)


class TestBlindIndex(unittest.TestCase):
    def test_deterministic_and_value_hiding(self):
        idx = blind_index("+15551234567")
        self.assertEqual(idx, blind_index("+15551234567"))
        self.assertNotIn(b"+15551234567", idx)

    def test_distinct_values_distinct_indexes(self):
        self.assertNotEqual(blind_index("a"), blind_index("b"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
