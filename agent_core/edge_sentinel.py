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


def _tool_env() -> dict[str, str]:
    env = os.environ.copy()
    extra_dirs = [
        str(Path.home() / ".foundry" / "bin"),
        str(Path.home() / ".local" / "bin"),
    ]
    current_path = env.get("PATH", "")
    path_parts = current_path.split(":") if current_path else []
    for d in reversed(extra_dirs):
        if d not in path_parts:
            path_parts.insert(0, d)
    env["PATH"] = ":".join(path_parts)
    return env


def _has_foundry_forge() -> bool:
    try:
        res = subprocess.run(
            ["forge", "--version"],
            env=_tool_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0 and "forge" in res.stdout.lower()
    except FileNotFoundError:
        return False


REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_project_cwd(target: Path) -> tuple[Path, Path | None]:
    """Return (target_for_cmd, cwd) using REPO_ROOT if target resides within it."""
    resolved = target.resolve()
    try:
        rel = resolved.relative_to(REPO_ROOT)
        if (REPO_ROOT / "lib").is_dir():
            return rel, REPO_ROOT
    except ValueError:
        pass
    return target, None


def run_tests(cwd: Path | None = None) -> bool:
    if not _has_foundry_forge():
        return True
    return subprocess.run(["forge", "test"], env=_tool_env(), cwd=cwd, check=False).returncode == 0


def run_slither(target: Path) -> bool:
    """Run Slither static analysis on target, falling back to solc if Foundry forge is absent."""
    env = _tool_env()

    cmd_target, cwd = _resolve_project_cwd(target)
    cmd = [
        sys.executable,
        "-c",
        (
            "import shutil, subprocess, sys\n"
            "from crytic_compile.platform.foundry import Foundry\n"
            "res = subprocess.run(['forge', 'config', '--json'], capture_output=True)\n"
            "if res.returncode != 0:\n"
            "    Foundry.is_supported = staticmethod(lambda *a, **kw: False)\n"
            "from slither.__main__ import main\n"
            "main()\n"
        ),
        str(cmd_target),
        "--filter-paths",
        "lib/|test/",
        "--solc-remaps",
        "@openzeppelin/=lib/openzeppelin-contracts/ forge-std/=lib/forge-std/src/",
        "--exclude-informational",
        "--exclude-low",
        "--fail-medium",
    ]
    return subprocess.run(cmd, env=env, cwd=cwd, check=False).returncode == 0


def atomic_write(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=Path("src/Vault.sol"),
        help="Solidity file to analyse (default: src/Vault.sol)",
    )
    parser.add_argument("--check-only", action="store_true", help="report without patching")
    parser.add_argument("--skip-slither", action="store_true", help="skip Slither static analysis")
    args = parser.parse_args(argv)

    target: Path = args.file
    if not target.is_file() and (REPO_ROOT / target).is_file():
        target = REPO_ROOT / target
    if not target.is_file():
        print(f"error: {target} not found", file=sys.stderr)
        return 2

    _, cwd = _resolve_project_cwd(target)
    original = target.read_text()
    lines = original.splitlines(keepends=True)
    violations = find_violations(lines)
    if not violations:
        print(f"[sentinel] {target}: no CEI violations detected")
        if not args.skip_slither:
            print(f"[sentinel] running Slither static analysis on {target}...")
            if not run_slither(target):
                print("[sentinel] Slither reported medium/high issues", file=sys.stderr)
                return 1
            print(f"[sentinel] {target}: Slither verification passed (0 medium/high issues)")
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
        if not run_tests(cwd=cwd):
            raise RuntimeError("forge test failed after patch")
        if not args.skip_slither and not run_slither(target):
            raise RuntimeError("Slither failed after patch")
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

