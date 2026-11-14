"""Tests for ToroidalTemplature, IQMempoolTransformer, Edge Sentinel, ScientificVaultOrchestrator, and Offline Node Mint Proof."""
from __future__ import annotations

import sys
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_core.offline_node_mint_proof import run_offline_mint_and_security_proof  # noqa: E402
from agent_core.scientific_vault_orchestrator import ScientificVaultOrchestrator  # noqa: E402
from quantum.iq_transformer import IQMempoolTransformer, ToroidalTemplature  # noqa: E402


def test_toroidal_templature_manifold_and_iq_transformer():
    templature = ToroidalTemplature(n_qubits=4, major_radius=2.0, minor_radius=1.0)
    raw = torch.tensor([[0.5, -0.5, 1.2, -1.2], [3.1, -3.1, 0.0, 1.5]])
    angles, tau = templature(raw)
    assert angles.shape == (2, 4)
    assert tau.shape == (2, 1)
    assert torch.all(tau > 0)
    assert torch.all(angles <= torch.pi + 1e-5)
    assert torch.all(angles >= -torch.pi - 1e-5)

    audit = templature.topology_audit()
    assert audit["manifold"] == "T^2 = S^1_toroidal x S^1_poloidal"
    assert audit["genus"] == 1
    assert audit["euler_characteristic"] == 0

    model = IQMempoolTransformer()
    x = torch.randn(3, 8)
    logits = model(x)
    assert logits.shape == (3, 3)
    metrics = model.toroidal_metrics(x)
    assert metrics["mean_templature"] > 0


def test_scientific_vault_orchestrator_verifies_clean_vault():
    orchestrator = ScientificVaultOrchestrator(skip_slither=True)
    report = orchestrator.run_scientific_workflow(REPO_ROOT / "src" / "Vault.sol", check_only=True)
    assert report.verdict == "VERIFIED_SAFE"
    assert report.repaired is False
    assert report.rolled_back is False
    assert len(report.stages) == 5
    assert len(report.digest_sha256) == 64


def test_scientific_vault_orchestrator_repairs_vulnerable_contract(tmp_path: Path):
    vuln_contract = tmp_path / "VulnerableVault.sol"
    vuln_contract.write_text(
        """// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

contract VulnerableVault {
    mapping(address => uint256) public balances;

    function withdraw(uint256 amount) external {
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "fail");
        balances[msg.sender] -= amount;
    }
}
""",
        encoding="utf-8",
    )

    orchestrator = ScientificVaultOrchestrator(skip_slither=True)
    report = orchestrator.run_scientific_workflow(vuln_contract)
    assert report.verdict == "REPAIRED_AND_VERIFIED"
    assert report.repaired is True
    assert report.rolled_back is False
    assert not vuln_contract.with_name("VulnerableVault.sol.bak").exists()

    repaired_text = vuln_contract.read_text(encoding="utf-8")
    assert repaired_text.index("balances[msg.sender] -= amount;") < repaired_text.index(".call{value: amount}")


def test_offline_node_mint_and_zero_dns_poisoning_proof():
    receipt = run_offline_mint_and_security_proof(run_foundry_cli=True)
    assert receipt["node_mode"] == "AIR_GAPPED_OFFLINE_EVM"
    assert receipt["network_isolation"]["dns_resolution_enabled"] is False
    assert receipt["network_isolation"]["external_sockets_enabled"] is False
    assert receipt["network_isolation"]["external_packets_sent"] == 0
    assert receipt["attack_simulations"]["dns_poisoning_attack_blocked"] is True
    assert receipt["attack_simulations"]["rogue_rpc_mitm_attack_blocked"] is True
    assert receipt["attack_simulations"]["reentrancy_drain_attack_blocked"] is True
    assert receipt["attack_simulations"]["duplicate_replay_mint_blocked"] is True
    assert receipt["attack_simulations"]["non_toroidal_topology_spoof_blocked"] is True
    assert receipt["total_minted"] == 4
    assert receipt["foundry_offline_evm_verified"] is True
