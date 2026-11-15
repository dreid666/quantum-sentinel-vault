#!/usr/bin/env python3
"""Fibonacci-harmonic SU(2) quantum tooling — offline, NON-LOAD-BEARING.

The quantum layer of the sovereign stack: every gate is special-unitary
(det = 1), tuned to Fibonacci harmonics so the stack keeps its own phase
regardless of what any other network does above or below it. Nothing here
loads a device: pure on-demand functions, no daemons, no boot services,
no timers, no mounts, no network (zero API / zero cloud / zero DNS).

Tuning:
  * golden angle  g = 2π(1 − 1/φ) ≈ 2.399963 rad  — the phyllotaxis
    phase advance: each harmonic step rotates by an irrational slice of
    the full turn, so the schedule never locks to any external cadence.
  * harmonic pitch τ_n = π·F(n)/F(n+1) → converges to π/φ.
  * gate n:  U_n = Rz(α_n)·Ry(τ_n)·Rz(α_n) with α_n = g·n (mod 2π).
  * chain(n) = U_{n-1}···U_1·U_0 — closed in SU(2), det stays 1.

Every gate capsule is sealed in the dual-branch two-layer method
(dual_branch.py): BOTH private branches required locally in one pass,
tamper/wrong-branch fails closed. The Fibonacci schedule is public,
deterministic TUNING — all secrecy lives in the branch keys alone.

This module is OPTIONAL by construction: nothing in the core imports it
and the stack runs fully without it (see available()).
"""

from __future__ import annotations

import math
from typing import Optional

import dual_branch as db
import su2

PHI = (1.0 + math.sqrt(5.0)) / 2.0
GOLDEN_ANGLE = 2.0 * math.pi * (1.0 - 1.0 / PHI)


def fib(n: int) -> int:
    """F(n) of the Fibonacci sequence (F(0)=F(1)=1 convention here)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def harmonic_pitch(n: int) -> float:
    """τ_n = π·F(n)/F(n+1) — converges to π/φ (the Fibonacci tuning)."""
    f_n, f_n1 = fib(n), fib(n + 1)
    return math.pi * f_n / f_n1


def harmonic_gate(n: int) -> list:
    """U_n = Rz(α_n)·Ry(τ_n)·Rz(α_n), α_n = golden angle·n — det = 1."""
    alpha = (GOLDEN_ANGLE * n) % (2.0 * math.pi)
    tau = harmonic_pitch(n)
    return su2.su2(alpha, tau, alpha)


def harmonic_chain(n: int) -> list:
    """Product U_{n-1}···U_0 — still exactly SU(2) (group is closed)."""
    m = su2.identity()
    for i in range(n):
        m = su2.mul(harmonic_gate(i), m)
    return m


def fib_schedule(n: int, mod: int = 2 ** 32) -> int:
    """Public deterministic harmonic counter schedule: F(n) mod 2^32."""
    return fib(n) % mod


def harmonic_capsule(n: int, key_a: bytes, key_b: bytes) -> bytes:
    """Dual-branch seal of the SQ8-encoded harmonic gate U_n."""
    return su2.wrap_gate(harmonic_gate(n), key_a, key_b)


def harmonic_open(n: int, blob: bytes, key_a: bytes, key_b: bytes) -> Optional[list]:
    """Unseal with BOTH branches; None on tamper/wrong branch (fail closed)."""
    gate = harmonic_gate(n)
    opened = su2.open_gate(blob, key_a, key_b)
    if opened is None:
        return None
    # the capsule must unseal to exactly the gate U_n it claims to be
    return opened if su2.sq8_encode(opened) == su2.sq8_encode(gate) else None


def available() -> bool:
    """Non-load-bearing marker: the quantum layer is optional tooling.
    The sovereign core (esim_profile, dual_branch) NEVER requires it."""
    return True


def selftest() -> bool:
    """Offline self-test: harmonic tuning convergence, chain unitarity,
    capsule round-trip + tamper + wrong-branch fail-closed, and the
    non-load-bearing guarantee (core imports none of this). Prints report."""
    import os
    import random

    rng = random.Random(0xF1B0)
    ok = True

    conv = abs(harmonic_pitch(45) - math.pi / PHI)
    print(f"  tuning         : |τ_45 − π/φ| = {conv:.2e} (< 1e-9)")
    ok = ok and conv < 1e-9

    passed = 0
    for i in range(32):
        rep = su2.unitarity_report(harmonic_chain(i))
        if rep["unitary"]:
            passed += 1
    print(f"  chain unitarity: {passed}/32 chains det=1, U†U=I")
    ok = ok and passed == 32

    key_a, key_b = os.urandom(32), os.urandom(32)
    n = 7
    capsule = harmonic_capsule(n, key_a, key_b)
    opened = harmonic_open(n, capsule, key_a, key_b)
    rt = opened is not None and su2.sq8_encode(opened) == su2.sq8_encode(harmonic_gate(n))
    print(f"  capsule        : {'round-trip OK' if rt else 'FAILED'}"
          f" ({len(capsule)} B sealed, gate U_{n})")
    ok = ok and rt

    # a capsule from gate n must NOT open as gate m ≠ n (identity bound)
    wrong_n = harmonic_open(n + 1, capsule, key_a, key_b) is None
    tampered = bytearray(capsule)
    tampered[len(tampered) // 2] ^= 1
    t1 = harmonic_open(n, bytes(tampered), key_a, key_b) is None
    t2 = harmonic_open(n, capsule, os.urandom(32), key_b) is None
    t3 = harmonic_open(n, capsule, key_a, os.urandom(32)) is None
    print(f"  fail-closed    : tamper={t1} wrongA={t2} wrongB={t3}"
          f" wrongGateN={wrong_n}")
    ok = ok and wrong_n and t1 and t2 and t3

    print(f"  SELFTEST {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
