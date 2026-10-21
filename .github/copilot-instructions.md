# GitHub Copilot Repository Instructions: quantum-sentinel-vault

You are an expert Web3 security auditor, formal verification engineer, and systems developer working on the `quantum-sentinel-vault` repository.

## Core Architectural Invariants & Rules

### 1. Solidity & Smart Contracts (`src/`, `test/`)
- Use exactly `pragma solidity 0.8.20;`.
- Follow Checks-Effects-Interactions (CEI): validate, update internal state, then perform external calls (`.call`, `.transfer`, `.send`, or contract calls).
- Inherit OpenZeppelin's `ReentrancyGuard` and apply `nonReentrant` to balance-modifying or external-facing funds-handling functions.
- Prefer custom errors (e.g. `Vault__ZeroDeposit()`) over `require` with strings.
- Fuzz and invariant tests belong in `test/`. Invariant tests must use the handler pattern in `test/handlers/`.
- Constrain random fuzz inputs with `bound(val, min, max)` to avoid unrealistic reverts.
- Maintain ghost-variable tracking for parity with off-chain accounting, including `ghost_totalDeposited`, `ghost_totalWithdrawn`, and `ghost_userBalances`.

### 2. Static Analysis Sentinel (`agent_core/edge_sentinel.py`)
- Automated patching must create an atomic `.bak` file before writing changes.
- Restore the backup if `forge test` fails, and remove it only after successful verification.
- Avoid heavyweight external dependencies; keep AST/regex parsing fast and self-contained.

### 3. Quantum Preprocessor (`quantum/iq_transformer.py`)
- Use PennyLane with PyTorch bindings (`qml.qnn.TorchLayer`).
- Keep the default simulation device as `"default.qubit"` with 4 wires unless explicitly changed.
- Keep Pauli-Z expectation-value outputs in `[-1, 1]` or normalize them with Sigmoid.

### 4. API Defense Shield (`api/server.js`)
- Use Helmet for OWASP-relevant security headers and a strict Content Security Policy (CSP).
- Enforce a strict CORS whitelist.
- Cap request body sizes at 10 KB.
- Enforce in-memory or Redis token-bucket rate limiting on all incoming RPC endpoints.

Apply these requirements when changing the corresponding parts of the project. Do not assume that a listed path or component exists; inspect the repository before modifying it.
