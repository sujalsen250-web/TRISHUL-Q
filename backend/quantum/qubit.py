"""Single-qubit state representation.

A qubit |psi> = alpha|0> + beta|1> with |alpha|^2 + |beta|^2 = 1 is stored
as a length-2 complex NumPy vector [alpha, beta].
"""
from __future__ import annotations

import numpy as np

KET0 = np.array([1.0, 0.0], dtype=complex)
KET1 = np.array([0.0, 1.0], dtype=complex)


def qubit(alpha: complex, beta: complex) -> np.ndarray:
    """Normalise (alpha, beta) and return the state vector."""
    v = np.array([complex(alpha), complex(beta)])
    norm = np.linalg.norm(v)
    if norm == 0:
        raise ValueError("Null state vector")
    return v / norm


def random_qubit(rng: np.random.Generator) -> np.ndarray:
    """Uniformly random pure state (Haar measure on the Bloch sphere)."""
    theta = np.arccos(2.0 * rng.random() - 1.0)   # polar angle
    phi = 2.0 * np.pi * rng.random()              # azimuthal angle
    return np.array(
        [np.cos(theta / 2.0), np.exp(1j * phi) * np.sin(theta / 2.0)], dtype=complex
    )


def probabilities(state: np.ndarray) -> tuple[float, float]:
    """Born rule: P(|0>) = |alpha|^2, P(|1>) = |beta|^2."""
    p = np.abs(state) ** 2
    total = p.sum()
    return float(p[0] / total), float(p[1] / total)


def fmt_state(state: np.ndarray, digits: int = 3) -> str:
    a, b = state[0], state[1]
    return f"{a.real:+.3f}{a.imag:+.3f}i|0⟩ {b.real:+.3f}{b.imag:+.3f}i|1⟩"


def fidelity(a: np.ndarray, b: np.ndarray) -> float:
    """|<a|b>|^2 -- 1.0 means the states are identical up to global phase."""
    return float(abs(np.vdot(a, b)) ** 2)
