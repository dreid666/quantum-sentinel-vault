#!/usr/bin/env bash
# bootstrap.sh - creates the complete quantum-sentinel-vault repository layout.
set -euo pipefail

mkdir -p .github/workflows agent_core src test/handlers quantum api paper docs

cat << 'EOF' > .github/workflows/security.yml
name: Security

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Install Foundry
        uses: foundry-rs/foundry-toolchain@v1

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Run edge sentinel
        run: python3 agent_core/edge_sentinel.py src/Vault.sol

      - name: Invariant tests
        run: forge test --match-contract VaultInvariantTest --invariant-runs 10000 --gas-report

      - name: Ensure no lingering backup file
        run: |
          if [ -f src/Vault.sol.bak ]; then
            echo "Lingering src/Vault.sol.bak found" >&2
            exit 1
          fi
EOF

cat << 'EOF' > .github/copilot-instructions.md
# Copilot Instructions

- Solidity: use exactly `pragma solidity 0.8.20;`.
- Follow Checks-Effects-Interactions (CEI): validate, mutate state, then perform external calls.
- Inherit OpenZeppelin `ReentrancyGuard` and apply `nonReentrant` to functions that send value.
- Use custom errors (e.g. `Vault__ZeroDeposit()`), never `require` with strings.
- Tests: Foundry invariant tests using the handler pattern with ghost ledgers
  (`ghost_totalDeposited`, `ghost_totalWithdrawn`, `ghost_userBalances`).
- `agent_core/edge_sentinel.py` must preserve atomic rollback: always create a `.bak`
  before patching, restore it if `forge test` fails, and remove it only after success.
EOF

cat << 'EOF' > agent_core/edge_sentinel.py
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
EOF
chmod +x agent_core/edge_sentinel.py

cat << 'EOF' > src/Vault.sol
// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract Vault is ReentrancyGuard {
    error Vault__ZeroDeposit();
    error Vault__InsufficientBalance();
    error Vault__TransferFailed();

    mapping(address => uint256) public balances;

    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);

    function deposit() external payable {
        if (msg.value == 0) revert Vault__ZeroDeposit();
        balances[msg.sender] += msg.value;
        emit Deposited(msg.sender, msg.value);
    }

    function withdraw(uint256 amount) external nonReentrant {
        // Checks
        if (balances[msg.sender] < amount) revert Vault__InsufficientBalance();
        // Effects
        balances[msg.sender] -= amount;
        emit Withdrawn(msg.sender, amount);
        // Interactions
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        if (!ok) revert Vault__TransferFailed();
    }
}
EOF

cat << 'EOF' > test/handlers/VaultHandler.sol
// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {CommonBase} from "forge-std/Base.sol";
import {StdCheats} from "forge-std/StdCheats.sol";
import {StdUtils} from "forge-std/StdUtils.sol";
import {Vault} from "../../src/Vault.sol";

contract VaultHandler is CommonBase, StdCheats, StdUtils {
    Vault public immutable vault;
    address[] public actors;

    uint256 public ghost_totalDeposited;
    uint256 public ghost_totalWithdrawn;
    mapping(address => uint256) public ghost_userBalances;

    constructor(Vault _vault) {
        vault = _vault;
        for (uint256 i = 0; i < 5; i++) {
            address actor = address(uint160(0xA000 + i));
            actors.push(actor);
            vm.deal(actor, 1_000 ether);
        }
    }

    function actorsLength() external view returns (uint256) {
        return actors.length;
    }

    function deposit(uint256 actorSeed, uint256 amount) external {
        address actor = actors[actorSeed % actors.length];
        amount = bound(amount, 1, 100 ether);
        if (actor.balance < amount) return;

        vm.prank(actor);
        vault.deposit{value: amount}();

        ghost_totalDeposited += amount;
        ghost_userBalances[actor] += amount;
    }

    function withdraw(uint256 actorSeed, uint256 amount) external {
        address actor = actors[actorSeed % actors.length];
        uint256 bal = ghost_userBalances[actor];
        if (bal == 0) return;
        amount = bound(amount, 1, bal);

        vm.prank(actor);
        vault.withdraw(amount);

        ghost_totalWithdrawn += amount;
        ghost_userBalances[actor] -= amount;
    }
}
EOF

cat << 'EOF' > test/Vault.invariant.t.sol
// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {Vault} from "../src/Vault.sol";
import {VaultHandler} from "./handlers/VaultHandler.sol";

contract VaultInvariantTest is StdInvariant, Test {
    Vault internal vault;
    VaultHandler internal handler;

    function setUp() public {
        vault = new Vault();
        handler = new VaultHandler(vault);
        targetContract(address(handler));
    }

    function invariant_balanceMatchesLedger() public view {
        assertEq(address(vault).balance, handler.ghost_totalDeposited() - handler.ghost_totalWithdrawn());
    }

    function invariant_sumOfBalancesMatchesEth() public view {
        uint256 sum;
        uint256 n = handler.actorsLength();
        for (uint256 i = 0; i < n; i++) {
            sum += vault.balances(handler.actors(i));
        }
        assertEq(sum, address(vault).balance);
    }
}
EOF

cat << 'EOF' > quantum/iq_transformer.py
"""Hybrid quantum-classical mempool model: 4-qubit VQC feeding a linear head."""
from __future__ import annotations

import pennylane as qml
import torch
from torch import nn

N_QUBITS = 4

_dev = qml.device("default.qubit", wires=N_QUBITS)


@qml.qnode(_dev, interface="torch", diff_method="backprop")
def _circuit(inputs, weights):
    qml.AngleEmbedding(inputs, wires=range(N_QUBITS), rotation="Y")
    for layer in range(weights.shape[0]):
        for w in range(N_QUBITS):
            qml.RY(weights[layer, w, 0], wires=w)
            qml.RZ(weights[layer, w, 1], wires=w)
        for w in range(N_QUBITS):
            qml.CNOT(wires=[w, (w + 1) % N_QUBITS])
    return [qml.expval(qml.PauliZ(w)) for w in range(N_QUBITS)]


class IQMempoolTransformer(nn.Module):
    def __init__(self, in_features: int = 8, n_layers: int = 2, n_classes: int = 3) -> None:
        super().__init__()
        self.encoder = nn.Linear(in_features, N_QUBITS)
        self.q_weights = nn.Parameter(0.1 * torch.randn(n_layers, N_QUBITS, 2))
        self.head = nn.Linear(N_QUBITS, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        angles = torch.tanh(self.encoder(x)) * torch.pi
        out = _circuit(angles, self.q_weights)
        q = torch.stack(list(out), dim=-1).to(x.dtype)
        return self.head(q)


if __name__ == "__main__":
    model = IQMempoolTransformer()
    print(model(torch.randn(2, 8)))
EOF

cat << 'EOF' > api/server.js
'use strict';

const express = require('express');
const helmet = require('helmet');
const cors = require('cors');

const PORT = process.env.PORT || 3000;
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || '').split(',').filter(Boolean);

const CAPACITY = 30;
const REFILL_PER_SEC = 5;
const buckets = new Map();

function rateLimiter(req, res, next) {
  const key = req.ip;
  const now = Date.now();
  let b = buckets.get(key);
  if (!b) {
    b = { tokens: CAPACITY, last: now };
    buckets.set(key, b);
  }
  b.tokens = Math.min(CAPACITY, b.tokens + ((now - b.last) / 1000) * REFILL_PER_SEC);
  b.last = now;
  if (b.tokens < 1) {
    res.set('Retry-After', String(Math.ceil((1 - b.tokens) / REFILL_PER_SEC)));
    return res.status(429).json({ error: 'Too Many Requests' });
  }
  b.tokens -= 1;
  return next();
}

setInterval(() => {
  const cutoff = Date.now() - 10 * 60 * 1000;
  for (const [k, v] of buckets) if (v.last < cutoff) buckets.delete(k);
}, 60 * 1000).unref();

const app = express();
app.disable('x-powered-by');

app.use(
  helmet({
    contentSecurityPolicy: {
      useDefaults: false,
      directives: {
        defaultSrc: ["'none'"],
        baseUri: ["'none'"],
        frameAncestors: ["'none'"],
        formAction: ["'none'"],
      },
    },
    referrerPolicy: { policy: 'no-referrer' },
    crossOriginResourcePolicy: { policy: 'same-origin' },
    hsts: { maxAge: 31536000, includeSubDomains: true, preload: true },
  })
);

app.use(
  cors({
    origin(origin, cb) {
      if (!origin || ALLOWED_ORIGINS.includes(origin)) return cb(null, true);
      return cb(new Error('Origin not allowed'));
    },
    methods: ['GET', 'POST'],
    allowedHeaders: ['Content-Type'],
    maxAge: 600,
  })
);

app.use(rateLimiter);
app.use(express.json({ limit: '10kb' }));

app.get('/health', (_req, res) => res.json({ status: 'ok' }));

// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  const status = err.status || (err.message === 'Origin not allowed' ? 403 : 500);
  res.status(status).json({ error: status === 500 ? 'Internal Server Error' : err.message });
});

if (require.main === module) {
  app.listen(PORT, () => console.log(`API listening on ${PORT}`));
}

module.exports = app;
EOF

cat << 'EOF' > paper/main.tex
\documentclass[conference]{IEEEtran}
\usepackage{amsmath,amssymb}
\usepackage{cite}

\begin{document}

\title{Quantum-Classical Architectures for Ethereum Mempool Forecasting}
\author{\IEEEauthorblockN{Quantum Sentinel Vault Team}}
\maketitle

\begin{abstract}
We present a hybrid architecture in which a four-qubit variational quantum circuit
encodes mempool features and feeds a classical classification head to forecast
transaction congestion and adversarial ordering behaviour.
\end{abstract}

\begin{IEEEkeywords}
variational quantum circuits, mempool, Ethereum, hybrid learning
\end{IEEEkeywords}

\section{Introduction}
Public mempools expose pending transactions to ordering attacks~\cite{daian2020flash}.
Variational quantum algorithms~\cite{cerezo2021variational} offer compact models that
can be trained end-to-end with classical networks~\cite{bergholm2018pennylane}.

\section{Architecture}
Classical features $x$ are projected to angles $\theta=\pi\tanh(Wx)$ and embedded by
rotations. Parameterized layers with CNOT entanglement produce expectations
$\langle Z_i\rangle$, which a linear head maps to class logits.

\section{Conclusion}
The hybrid design is a lightweight baseline for quantum-classical mempool forecasting.

\bibliographystyle{IEEEtran}
\bibliography{references}

\end{document}
EOF

cat << 'EOF' > paper/references.bib
@inproceedings{daian2020flash,
  author    = {Daian, Philip and Goldfeder, Steven and Kell, Tyler and Li, Yunqi and Zhao, Xueyuan and Bentov, Iddo and Breidenbach, Lorenz and Juels, Ari},
  title     = {Flash Boys 2.0: Frontrunning in Decentralized Exchanges, Miner Extractable Value, and Consensus Instability},
  booktitle = {IEEE Symposium on Security and Privacy},
  year      = {2020}
}

@article{cerezo2021variational,
  author  = {Cerezo, M. and Arrasmith, A. and Babbush, R. and others},
  title   = {Variational Quantum Algorithms},
  journal = {Nature Reviews Physics},
  volume  = {3},
  pages   = {625--644},
  year    = {2021}
}

@article{bergholm2018pennylane,
  author  = {Bergholm, Ville and others},
  title   = {PennyLane: Automatic differentiation of hybrid quantum-classical computations},
  journal = {arXiv preprint arXiv:1811.04968},
  year    = {2018}
}
EOF

cat << 'EOF' > foundry.toml
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
solc_version = "0.8.20"
optimizer = true
optimizer_runs = 200

[invariant]
runs = 10000
depth = 128
fail_on_revert = false
EOF

cat << 'EOF' > package.json
{
  "name": "quantum-sentinel-vault-api",
  "version": "1.0.0",
  "private": true,
  "main": "api/server.js",
  "scripts": {
    "start": "node api/server.js"
  },
  "engines": {
    "node": ">=18"
  },
  "dependencies": {
    "cors": "^2.8.5",
    "express": "^4.19.2",
    "helmet": "^7.1.0"
  }
}
EOF

cat << 'EOF' > requirements.txt
torch
pennylane
numpy
scipy
EOF

cat << 'EOF' > remappings.txt
@openzeppelin/=lib/openzeppelin-contracts/
forge-std/=lib/forge-std/src/
EOF

cat << 'EOF' > .gitignore
# Foundry
out/
cache/
broadcast/

# Node
node_modules/
npm-debug.log*

# Python
__pycache__/
*.py[cod]
.venv/
venv/

# Build artifacts
*.bak
*.tmp
EOF

cat << 'EOF' > docs/INDEX.md
# Documentation Index

- [ROADMAP](ROADMAP.md)
- `src/Vault.sol` - CEI-compliant ETH vault
- `test/` - Foundry invariant suite (handler + ghost ledgers)
- `agent_core/edge_sentinel.py` - CEI violation detector/patcher with atomic rollback
- `quantum/iq_transformer.py` - hybrid VQC mempool model
- `api/server.js` - hardened Express API
- `paper/` - IEEEtran preprint

## Setup

Install dependencies:

    forge install OpenZeppelin/openzeppelin-contracts foundry-rs/forge-std --no-commit
    pip install -r requirements.txt
    npm install
EOF

cat << 'EOF' > docs/ROADMAP.md
# Roadmap

1. **v0.1** - Vault, invariant suite, edge sentinel, CI.
2. **v0.2** - Train and benchmark `IQMempoolTransformer` on real mempool data.
3. **v0.3** - Authenticated API endpoints serving forecasts.
4. **v1.0** - External audit and paper submission.
EOF

echo "quantum-sentinel-vault scaffold created."
echo "Next: forge install OpenZeppelin/openzeppelin-contracts foundry-rs/forge-std"
