# Copilot Instructions

- Solidity: use exactly `pragma solidity 0.8.20;`.
- Follow Checks-Effects-Interactions (CEI): validate, mutate state, then perform external calls.
- Inherit OpenZeppelin `ReentrancyGuard` and apply `nonReentrant` to functions that send value.
- Use custom errors (e.g. `Vault__ZeroDeposit()`), never `require` with strings.
- Tests: Foundry invariant tests using the handler pattern with ghost ledgers
  (`ghost_totalDeposited`, `ghost_totalWithdrawn`, `ghost_userBalances`).
- `agent_core/edge_sentinel.py` must preserve atomic rollback: always create a `.bak`
  before patching, restore it if `forge test` fails, and remove it only after success.
