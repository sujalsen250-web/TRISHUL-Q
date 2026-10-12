"""Pauli operators and teleportation correction logic.

Standard teleportation correction table (Bell pair = Φ+):
    00 -> I     (no correction)
    01 -> X     (bit flip)
    10 -> Z     (phase flip)
    11 -> XZ    (bit + phase flip)
"""
from __future__ import annotations

import numpy as np

I = np.array([[1, 0], [0, 1]], dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)

PAULI = {"I": I, "X": X, "Y": Y, "Z": Z}

CORRECTION_MAP = {
    "00": "I",
    "01": "X",
    "10": "Z",
    "11": "XZ",
}

_CORRECTION_CANDIDATES = ["I", "X", "Z", "XZ", "ZX", "Y"]


def correction_for_bits(bits: str) -> str:
    """Protocol-defined correction for a two-bit Bell measurement outcome."""
    return CORRECTION_MAP.get(bits, "I")


def apply_operation(state: np.ndarray, op: str) -> np.ndarray:
    """Apply a (possibly composed) Pauli operation, e.g. 'XZ' = X·Z."""
    for letter in reversed(op):
        state = PAULI[letter] @ state
    return state


def best_correction(bob_state: np.ndarray, target: np.ndarray) -> tuple[str, float]:
    """Pick the Pauli op that recovers `target` from `bob_state`.

    Used generically for every Bell pair (the standard table only holds for
    the Φ+ channel); the chosen op maximise |<target| op |bob>|^2.
    """
    best_op, best_f = "I", -1.0
    for op in _CORRECTION_CANDIDATES:
        f = float(abs(np.vdot(target, apply_operation(bob_state, op))) ** 2)
        if f > best_f:
            best_op, best_f = op, f
    return best_op, best_f


def describe(op: str) -> str:
    names = {"I": "Pauli-I (identity)", "X": "Pauli-X (bit flip)",
             "Y": "Pauli-Y", "Z": "Pauli-Z (phase flip)"}
    if op in names:
        return names[op]
    return "Pauli-" + "·".join(op)
