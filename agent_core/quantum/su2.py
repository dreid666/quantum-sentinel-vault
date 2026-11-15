#!/usr/bin/env python3
"""SU(2) quantum gate functionality — offline, SQ8-fixed-point, dual-branch
sealed.

SU(2) special-unitary gates via Euler construction U = Rz(a)·Ry(t)·Rz(c)
(det = 1 for all angles). Gates are encoded in deterministic SQ8 fixed point
(int8, scale 127) per the Master Architectural Compendium, and every sealed
gate capsule is wrapped in the dual-branch two-layer method:
unsealing requires BOTH private branches locally in one pass; wrong branches
or tamper fail closed. No network, no API, no cloud, no DNS.
"""

from __future__ import annotations

import math
from typing import Optional

import dual_branch as db

# complex amplitude as (re, im) tuples; matrix as 4 pairs row-major
# [m00, m01, m10, m11]

SQ8_SCALE = 127.0


def rz(angle: float) -> list:
    """Rz(θ) = diag(e^{-iθ/2}, e^{+iθ/2}) — det = 1."""
    c, s = math.cos(angle / 2.0), math.sin(angle / 2.0)
    return [[(c, -s), (0.0, 0.0)], [(0.0, 0.0), (c, s)]]


def ry(angle: float) -> list:
    """Ry(θ) — real rotation, det = 1."""
    c, s = math.cos(angle / 2.0), math.sin(angle / 2.0)
    return [[(c, 0.0), (-s, 0.0)], [(s, 0.0), (c, 0.0)]]


def mul(a: list, b: list) -> list:
    """2x2 complex matrix multiply."""
    out = []
    for i in range(2):
        row = []
        for j in range(2):
            re = im = 0.0
            for k in range(2):
                ar, ai = a[i][k]
                br, bi = b[k][j]
                re += ar * br - ai * bi
                im += ar * bi + ai * br
            row.append((re, im))
        out.append(row)
    return out


def su2(a: float, t: float, c: float) -> list:
    """General SU(2): U = Rz(a)·Ry(t)·Rz(c). det = 1 by construction."""
    return mul(rz(a), mul(ry(t), rz(c)))


def identity() -> list:
    return [[(1.0, 0.0), (0.0, 0.0)], [(0.0, 0.0), (1.0, 0.0)]]


def det2(m: list) -> complex:
    (a, b), (c, d) = [(m[i][j] for j in range(2)) for i in range(2)]
    ar, ai = m[0][0]; br, bi = m[0][1]; cr, ci = m[1][0]; dr, di = m[1][1]
    return complex(ar * dr - ai * di, ar * di + ai * dr) - complex(
        br * cr - bi * ci, br * ci + bi * cr
    )


def unitarity_report(m: list) -> dict:
    """|det| deviation from 1 and U†U deviation from I (both ≈ 0 for SU(2))."""
    d = det2(m)
    det_err = abs(abs(d) - 1.0)
    # M†M
    mdag = [[_conj(m[0][0]), _conj(m[1][0])], [_conj(m[0][1]), _conj(m[1][1])]]
    prod = mul(mdag, m)
    eye_err = max(
        abs(prod[i][j][0] - (1.0 if i == j else 0.0)) +
        abs(prod[i][j][1]) for i in range(2) for j in range(2)
    )
    return {"det_abs": abs(d), "det_err": det_err, "eye_err": eye_err,
            "unitary": det_err < 1e-9 and eye_err < 1e-9}


def _conj(x: tuple) -> tuple:
    return (x[0], -x[1])


def apply(m: list, state: tuple) -> tuple:
    """Apply SU(2) to a single-qubit state (a0, a1) of complex amplitudes."""
    (a0r, a0i), (a1r, a1i) = state
    (m00, m01), (m10, m11) = m
    def cm(mv, sv):
        return (mv[0] * sv[0] - mv[1] * sv[1], mv[0] * sv[1] + mv[1] * sv[0])
    o0 = (cm(m00, (a0r, a0i))[0] + cm(m01, (a1r, a1i))[0],
          cm(m00, (a0r, a0i))[1] + cm(m01, (a1r, a1i))[1])
    o1 = (cm(m10, (a0r, a0i))[0] + cm(m11, (a1r, a1i))[0],
          cm(m10, (a0r, a0i))[1] + cm(m11, (a1r, a1i))[1])
    return (o0, o1)


def sq8_encode(m: list) -> bytes:
    """Deterministic SQ8 (int8, scale 127) encoding, row-major re/im pairs."""
    out = bytearray()
    for i in range(2):
        for j in range(2):
            for v in m[i][j]:
                q = max(-127, min(127, int(round(v * SQ8_SCALE))))
                out += q.to_bytes(1, "big", signed=True)
    return bytes(out)


def sq8_decode(blob: bytes) -> list:
    vals = [int.from_bytes(blob[i:i + 1], "big", signed=True) / SQ8_SCALE
            for i in range(8)]
    return [[(vals[0], vals[1]), (vals[2], vals[3])],
            [(vals[4], vals[5]), (vals[6], vals[7])]]


def wrap_gate(m: list, key_a: bytes, key_b: bytes) -> bytes:
    """Dual-branch seal of an SQ8-encoded SU(2) gate (the encrypted layering)."""
    return db.seal(key_a, key_b, sq8_encode(m))


def open_gate(blob: bytes, key_a: bytes, key_b: bytes) -> Optional[list]:
    """Unseal with BOTH branches; None on tamper/wrong branch (fail closed)."""
    data = db.unseal(key_a, key_b, blob)
    if data is None or len(data) != 8:
        return None
    return sq8_decode(data)


def selftest() -> bool:
    """End-to-end offline self-test: SU(2) unitarity, SQ8 fidelity, dual-branch
    capsule round-trip + tamper + wrong-branch rejection. Prints a report."""
    import os
    import random

    rng = random.Random(0x5132)
    ok = True

    for i in range(64):
        a, t, c = (rng.uniform(-2 * math.pi, 2 * math.pi) for _ in range(3))
        m = su2(a, t, c)
        rep = unitarity_report(m)
        if not rep["unitary"]:
            ok = False
            print(f"  FAIL unitarity: {rep}")
    print(f"  unitarity      : 64/64 random SU(2) gates det=1, U†U=I"
          if ok else "  unitarity      : FAILED")

    gate = su2(math.pi / 4, math.pi / 3, -math.pi / 4)
    sq = sq8_encode(gate)
    back = sq8_decode(sq)
    err = max(abs(gate[i][j][k] - back[i][j][k]) for i in range(2)
              for j in range(2) for k in range(2))
    print(f"  SQ8 fidelity   : max matrix error {err:.5f} (Q7 bound ~0.011)")
    ok = ok and err < 0.02

    key_a, key_b = os.urandom(32), os.urandom(32)
    capsule = wrap_gate(gate, key_a, key_b)
    opened = open_gate(capsule, key_a, key_b)
    rt = opened is not None and sq8_encode(opened) == sq
    print(f"  capsule        : {'round-trip OK' if rt else 'FAILED'}"
          f" ({len(capsule)} bytes sealed)")
    ok = ok and rt

    tampered = bytearray(capsule); tampered[len(tampered) // 2] ^= 1
    t1 = open_gate(bytes(tampered), key_a, key_b) is None
    t2 = open_gate(capsule, os.urandom(32), key_b) is None
    t3 = open_gate(capsule, key_a, os.urandom(32)) is None
    print(f"  fail-closed    : tamper={t1} wrongA={t2} wrongB={t3}")
    ok = ok and t1 and t2 and t3

    print(f"  SELFTEST {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
