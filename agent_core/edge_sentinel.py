#!/usr/bin/env python3
"""Edge Sentinel: detects and auto-fixes CEI ordering violations in Solidity files.

A violation is an external call (`.call{`, `.call(`, `.transfer(`, `.send(`) that occurs
before a state mutation such as `balances[msg.sender] -= amount;` within one function.
The patch is applied atomically with a `.bak` backup and rolled back if `forge test` fails.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXTERNAL_CALL = re.compile(r"\.(call|transfer|send|delegatecall)\s*[\({]")
STATE_MUTATION = re.compile(r"^\s*[A-Za-z_]\w*\s*(\[[^\]]*\]\s*)+(-=|\+=|=)(?!=)[^;]*;")
FUNC_START = re.compile(r"^\s*function\s+\w+")


def find_violations(lines: list[str]) -> list[tuple[int, int]]:
    """Return (call_index, mutation_index) pairs where a call precedes a mutation."""
    violations: list[tuple[int, int]] = []
    in_func = False
    depth = 0
    call_idx: int | None = None
    for i, line in enumerate(lines):
        if not in_func and FUNC_START.match(line):
            in_func, depth, call_idx = True, 0, None
        if not in_func:
            continue
        if call_idx is None and EXTERNAL_CALL.search(line):
            call_idx = i
        elif call_idx is not None and STATE_MUTATION.match(line):
            violations.append((call_idx, i))
            call_idx = None
        depth += line.count("{") - line.count("}")
        if depth <= 0 and "}" in line and i > 0 and not FUNC_START.match(line):
            in_func, call_idx = False, None
    return violations


def call_block_end(lines: list[str], start: int, limit: int) -> int:
    """Index of the last line of the statement(s) forming the external-call block."""
    end = start
    while end < limit and ";" not in lines[end]:
        end += 1
    return end


def patch(lines: list[str], call_idx: int, mut_idx: int) -> list[str]:
    """Move the mutation line so it sits before the external call statement."""
    mutation = lines[mut_idx]
    rest = lines[:mut_idx] + lines[mut_idx + 1:]
    return rest[:call_idx] + [mutation] + rest[call_idx:]


def run_tests() -> bool:
    return subprocess.run(["forge", "test"], check=False).returncode == 0


def atomic_write(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Solidity file to analyse")
    parser.add_argument("--check-only", action="store_true", help="report without patching")
    args = parser.parse_args(argv)

    target: Path = args.file
    if not target.is_file():
        print(f"error: {target} not found", file=sys.stderr)
        return 2

    original = target.read_text()
    lines = original.splitlines(keepends=True)
    violations = find_violations(lines)
    if not violations:
        print(f"[sentinel] {target}: no CEI violations detected")
        return 0

    for c, m in violations:
        print(f"[sentinel] CEI violation: external call line {c + 1} precedes state mutation line {m + 1}")
    if args.check_only:
        return 1

    backup = target.with_name(target.name + ".bak")
    shutil.copy2(target, backup)
    try:
        # Apply from the bottom up so earlier line indices stay valid.
        for c, m in sorted(violations, reverse=True):
            lines = patch(lines, c, m)
        atomic_write(target, "".join(lines))
        if not run_tests():
            raise RuntimeError("forge test failed after patch")
    except Exception as exc:  # noqa: BLE001 - rollback on any failure
        shutil.copy2(backup, target)
        backup.unlink(missing_ok=True)
        print(f"[sentinel] rolled back: {exc}", file=sys.stderr)
        return 1

    backup.unlink(missing_ok=True)
    print("[sentinel] patched and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
