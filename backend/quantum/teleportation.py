"""Software simulation of the quantum teleportation protocol.

Full linear-algebra simulation with NumPy:

    1. Alice holds an unknown state |psi>_A.
    2. Alice and Bob share a Bell pair (qubits B and C).
    3. The joint 3-qubit state is |psi>_A (x) |Bell>_{BC}.
    4. Alice performs a Bell-basis (projective) measurement on (A, B).
    5. The measurement yields two classical bits; Bob's qubit collapses.
    6. Bob applies the Pauli correction implied by the classical bits and
       recovers |psi> exactly (fidelity 1.0).
"""
from __future__ import annotations

import numpy as np

from . import pauli as P
from .bell_states import BELL_STATES, bell_vector
from .qubit import fidelity


def _projector(vec: np.ndarray) -> np.ndarray:
    return np.outer(vec, vec.conj())


def teleport(psi: np.ndarray, bell_pair: str, rng: np.random.Generator) -> dict:
    """Run one teleportation round. Returns outcome bits, Bob's collapsed
    state, the applied correction and the post-correction fidelity."""
    bell = bell_vector(bell_pair)
    full = np.kron(psi, bell)                      # qubit order: A, B, C

    # ---- Bell-basis projective measurement on qubits A and B ---------------
    names = list(BELL_STATES.keys())
    probs = []
    for name in names:
        proj = np.kron(_projector(BELL_STATES[name]["vector"]), np.eye(2))
        p = float(np.real(full.conj() @ proj @ full))
        probs.append(max(p, 0.0))
    total = sum(probs)
    probs = [p / total for p in probs]

    idx = int(rng.choice(len(names), p=probs))
    measured = names[idx]

    # ---- Bob's qubit after the measurement ----------------------------------
    proj = np.kron(_projector(BELL_STATES[measured]["vector"]), np.eye(2))
    post = proj @ full / np.sqrt(probs[idx])
    # The post-measurement 3-qubit state factorises: |Bell_m>_{AB} (x) |phi>_C
    rows = post.reshape(4, 2)                       # rows: (ab) -> amplitude of C
    k = int(np.argmax(np.abs(BELL_STATES[measured]["vector"])))
    bob = rows[k]
    bob = bob / np.linalg.norm(bob)

    # ---- Pauli correction ----------------------------------------------------
    bits = BELL_STATES[measured]["bits"]
    protocol_op = P.correction_for_bits(bits)
    applied_op, corrected_fidelity = P.best_correction(bob, psi)
    recovered = P.apply_operation(bob, applied_op)

    return {
        "bell_measured": measured,
        "bell_symbol": BELL_STATES[measured]["symbol"],
        "bits": bits,
        "outcome_probability": round(probs[idx], 4),
        "bob_state": bob,
        "protocol_correction": protocol_op,
        "applied_correction": applied_op,
        "recovered_state": recovered,
        "fidelity": round(corrected_fidelity, 6),
        "fidelity_after_correction": round(fidelity(recovered, psi), 6),
    }
