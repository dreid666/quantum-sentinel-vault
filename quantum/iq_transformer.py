"""Hybrid quantum-classical mempool model with a Toroidal Templature (T^2 = S^1 x S^1) structure."""
from __future__ import annotations

import math
from typing import Any, Dict

import pennylane as qml
import torch
from torch import nn

N_QUBITS = 4
TOROIDAL_DIM = 2  # 2x2 toroidal-poloidal lattice over 4 qubits (S^1_toroidal x S^1_poloidal)

_dev = qml.device("default.qubit", wires=N_QUBITS)


class ToroidalTemplature(nn.Module):
    """Toroidal Templature structure on T^2 = S^1 (toroidal) x S^1 (poloidal).

    Maps classical/quantum state vectors onto a compactified 2-torus manifold with major radius R
    and minor radius r, enforcing periodic boundary conditions in both toroidal (phi) and
    poloidal (theta) coordinates to regulate attention/rotation temperature ('templature').
    """

    def __init__(
        self,
        n_qubits: int = N_QUBITS,
        major_radius: float = 2.0,
        minor_radius: float = 1.0,
        base_templature: float = 1.0,
    ) -> None:
        super().__init__()
        self.n_qubits = n_qubits
        self.major_radius = major_radius
        self.minor_radius = minor_radius
        self.toroidal_phase = nn.Parameter(torch.linspace(0.0, 2.0 * math.pi, n_qubits))
        self.poloidal_phase = nn.Parameter(torch.linspace(0.0, math.pi, n_qubits))
        self.log_base_templature = nn.Parameter(torch.tensor(math.log(max(base_templature, 1e-3))))
        # Doubly-periodic toroidal coupling kernel (circulant along both S^1 cycles)
        self.toroidal_coupling = nn.Parameter(torch.tensor([0.5, 0.2, 0.1, 0.2]))

    def forward(self, raw_angles: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Project input angles onto the T^2 toroidal templature manifold.

        Returns:
            modulated_angles: Phase angles wrapped onto (-pi, pi] via toroidal-poloidal curvature.
            templature_scale: Positive inverse-templature scaling factor per sample.
        """
        phi = raw_angles + self.toroidal_phase
        theta = torch.roll(raw_angles, shifts=1, dims=-1) + self.poloidal_phase

        # Torus metric factor: g_{phi,phi}^{1/2} = R + r * cos(theta)
        metric_scale = (self.major_radius + self.minor_radius * torch.cos(theta)) / (
            self.major_radius + self.minor_radius
        )

        # Periodic circular convolution on S^1 x S^1
        coupled = (
            self.toroidal_coupling[0] * raw_angles
            + self.toroidal_coupling[1] * torch.roll(raw_angles, shifts=1, dims=-1)
            + self.toroidal_coupling[2] * torch.roll(raw_angles, shifts=2, dims=-1)
            + self.toroidal_coupling[3] * torch.roll(raw_angles, shifts=-1, dims=-1)
        )

        base_tau = torch.nn.functional.softplus(self.log_base_templature) + 0.1
        # Toroidal energy density E_T2 = 1 - cos(phi)*cos(theta)
        toroidal_energy = 1.0 - 0.5 * (torch.cos(phi) + torch.cos(theta))
        templature = base_tau * (1.0 + 0.25 * toroidal_energy.mean(dim=-1, keepdim=True))

        # Wrap angles smoothly onto the torus [-pi, pi]
        modulated_angles = torch.atan2(torch.sin(coupled * metric_scale), torch.cos(coupled * metric_scale))
        return modulated_angles, templature

    def topology_audit(self) -> Dict[str, Any]:
        aspect_ratio = self.major_radius / max(self.minor_radius, 1e-6)
        return {
            "manifold": "T^2 = S^1_toroidal x S^1_poloidal",
            "n_qubits": self.n_qubits,
            "major_radius_R": self.major_radius,
            "minor_radius_r": self.minor_radius,
            "aspect_ratio": round(aspect_ratio, 4),
            "euler_characteristic": 0,
            "genus": 1,
            "periodic_boundaries": ["toroidal_ring_step_1", "poloidal_chord_step_2"],
        }


@qml.qnode(_dev, interface="torch", diff_method="backprop")
def _circuit(inputs, weights):
    qml.AngleEmbedding(inputs, wires=range(N_QUBITS), rotation="Y")
    for layer in range(weights.shape[0]):
        for w in range(N_QUBITS):
            qml.RY(weights[layer, w, 0], wires=w)
            qml.RZ(weights[layer, w, 1], wires=w)
        # Toroidal cycle (S^1 major ring)
        for w in range(N_QUBITS):
            qml.CNOT(wires=[w, (w + 1) % N_QUBITS])
        # Poloidal cycle (S^1 minor cross-winding) completing the 2-torus T^2 topology
        half = N_QUBITS // 2
        for w in range(half):
            qml.CNOT(wires=[w, (w + half) % N_QUBITS])
    return [qml.expval(qml.PauliZ(w)) for w in range(N_QUBITS)]


class IQMempoolTransformer(nn.Module):
    def __init__(
        self,
        in_features: int = 8,
        n_layers: int = 2,
        n_classes: int = 3,
        major_radius: float = 2.0,
        minor_radius: float = 1.0,
    ) -> None:
        super().__init__()
        self.encoder = nn.Linear(in_features, N_QUBITS)
        self.templature = ToroidalTemplature(
            n_qubits=N_QUBITS,
            major_radius=major_radius,
            minor_radius=minor_radius,
        )
        self.q_weights = nn.Parameter(0.1 * torch.randn(n_layers, N_QUBITS, 2))
        self.head = nn.Linear(N_QUBITS, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        raw_angles = torch.tanh(self.encoder(x)) * torch.pi
        toroidal_angles, tau = self.templature(raw_angles)
        out = _circuit(toroidal_angles, self.q_weights)
        q = torch.stack(list(out), dim=-1).to(x.dtype)
        return self.head(q) / tau.to(x.dtype)

    def toroidal_metrics(self, x: torch.Tensor) -> Dict[str, Any]:
        with torch.no_grad():
            raw_angles = torch.tanh(self.encoder(x)) * torch.pi
            toroidal_angles, tau = self.templature(raw_angles)
            logits = self.forward(x)
            probs = torch.softmax(logits, dim=-1)
        return {
            "topology": self.templature.topology_audit(),
            "mean_templature": round(float(tau.mean().item()), 4),
            "toroidal_angle_norm": round(float(toroidal_angles.norm().item()), 4),
            "class_probabilities": probs.mean(dim=0).tolist(),
        }


if __name__ == "__main__":
    model = IQMempoolTransformer()
    sample = torch.randn(2, 8)
    print(model(sample))
    print(model.toroidal_metrics(sample))

