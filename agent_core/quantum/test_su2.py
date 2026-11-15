#!/usr/bin/env python3
"""Unit tests for SU(2) quantum gates + SQ8 + dual-branch capsule wrapping."""

import math
import os
import random
import unittest

from su2 import (  # noqa: E402
    SQ8_SCALE,
    apply,
    identity,
    open_gate,
    rz,
    ry,
    sq8_decode,
    sq8_encode,
    su2,
    unitarity_report,
    wrap_gate,
)


class TestSU2Math(unittest.TestCase):
    def test_identity_is_su2(self):
        rep = unitarity_report(identity())
        self.assertTrue(rep["unitary"])

    def test_random_gates_unitary(self):
        rng = random.Random(1)
        for _ in range(64):
            m = su2(*(rng.uniform(-2 * math.pi, 2 * math.pi) for _ in range(3)))
            rep = unitarity_report(m)
            self.assertTrue(rep["unitary"], msg=f"det={rep['det_abs']}")
            self.assertLess(rep["det_err"], 1e-9)

    def test_rz_ry_det_exactly_one(self):
        for m in (rz(0.7), ry(1.3)):
            self.assertAlmostEqual(abs(unitarity_report(m)["det_abs"]), 1.0, places=9)

    def test_apply_zero_state_consistent_norm(self):
        # |0> -> U|0> must stay normalized (SU(2) preserves the 2-norm)
        m = su2(0.3, 1.1, -0.9)
        out = apply(m, ((1.0, 0.0), (0.0, 0.0)))
        norm = math.sqrt(sum(x[0] ** 2 + x[1] ** 2 for x in out))
        self.assertAlmostEqual(norm, 1.0, places=9)

    def test_rz_pi_on_plus_state_swaps_phase(self):
        # Rz(π)|+> = (e^{-iπ/2}, e^{iπ/2})/√2 — a global phase of -1 on the
        # equal superposition; magnitudes unchanged
        m = rz(math.pi)
        out = apply(m, ((1 / math.sqrt(2), 0.0), (1 / math.sqrt(2), 0.0)))
        mag = lambda z: math.hypot(z[0], z[1])
        self.assertAlmostEqual(mag(out[0]), 1 / math.sqrt(2), places=9)
        self.assertAlmostEqual(mag(out[1]), 1 / math.sqrt(2), places=9)


class TestSQ8(unittest.TestCase):
    def test_roundtrip_fidelity(self):
        rng = random.Random(2)
        worst = 0.0
        for _ in range(16):
            m = su2(*(rng.uniform(-2 * math.pi, 2 * math.pi) for _ in range(3)))
            back = sq8_decode(sq8_encode(m))
            worst = max(
                worst,
                max(abs(m[i][j][k] - back[i][j][k])
                    for i in range(2) for j in range(2) for k in range(2)),
            )
        self.assertLess(worst, 0.02)  # Q7 quantization bound is ~1/(2*127)

    def test_encoding_is_8_bytes_deterministic(self):
        m = su2(0.2, 0.4, 0.6)
        blob = sq8_encode(m)
        self.assertEqual(len(blob), 8)
        self.assertEqual(blob, sq8_encode(m))

    def test_scale_is_127(self):
        self.assertEqual(SQ8_SCALE, 127.0)


class TestDualBranchCapsule(unittest.TestCase):
    def setUp(self):
        self.ka, self.kb = os.urandom(32), os.urandom(32)
        self.gate = su2(math.pi / 4, math.pi / 3, -math.pi / 4)
        self.capsule = wrap_gate(self.gate, self.ka, self.kb)

    def test_roundtrip_preserves_sq8_bytes(self):
        opened = open_gate(self.capsule, self.ka, self.kb)
        self.assertIsNotNone(opened)
        self.assertEqual(sq8_encode(opened), sq8_encode(self.gate))

    def test_single_branch_fails_closed(self):
        self.assertIsNone(open_gate(self.capsule, os.urandom(32), self.kb))
        self.assertIsNone(open_gate(self.capsule, self.ka, os.urandom(32)))

    def test_tamper_fails_closed(self):
        for pos in (0, 16, len(self.capsule) // 2, len(self.capsule) - 1):
            bad = bytearray(self.capsule)
            bad[pos] ^= 0x01
            self.assertIsNone(open_gate(bytes(bad), self.ka, self.kb), f"pos={pos}")

    def test_capsule_is_sealed(self):
        # gate bytes must not appear raw in the capsule (encrypted layering)
        self.assertNotIn(sq8_encode(self.gate), self.capsule)


if __name__ == "__main__":
    unittest.main(verbosity=2)
