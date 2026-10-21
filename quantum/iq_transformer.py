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
