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
