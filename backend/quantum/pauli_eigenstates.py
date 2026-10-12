"""Pauli-eigenstate public key for the v8 QDS protocol.

Motivation (SIH26141)
---------------------
The v7 verifier only measured the Z-basis of a single reference qubit.  v8
extends the protocol to the full Gottesman-Chuang / teleportation-QDS check:

  * Alice prepares every signature qubit in a random Pauli eigenstate --
    one of the six states that are +1 / -1 eigenstates of X, Y or Z:

        Z-basis : |0>  (bit 0) , |1>  (bit 1)
        X-basis : |+>  (bit 0) , |->  (bit 1)
        Y-basis : |+i> (bit 0) , |-i> (bit 1)

  * the eigenstate is teleported to Bob (existing teleportation module);
  * Bob measures each qubit in a RANDOMLY chosen Pauli basis (X/Y/Z):
        - basis MATCHES Alice's preparation -> the outcome is the
          DETERMINISTIC eigenvalue, so it can be CHECKED;
        - basis MISMATCHES -> the outcome is uniformly random, so the qubit
          is DISCARDED from the check.

Because the six states are pairwise non-orthogonal across different bases,
a forger who does not hold the actual quantum states cannot reproduce the
eigenvalues on the checked qubits: by the no-cloning / uncertainty argument
each basis-agnostic guess succeeds with probability 1/2.  This is exactly the
statistical hardness that makes P_forge fall exponentially in the number of
checks (see detection.forgery).

Nothing here is hardcoded per attack: every outcome is sampled from the
actual state vectors with NumPy.
"""
from __future__ import annotations

import numpy as np

_S = 1.0 / np.sqrt(2.0)

# (basis, eigenvalue-bit) -> state vector.  Bit 0 = +1 eigenvalue,
# bit 1 = -1 eigenvalue of the given Pauli operator.
EIGENSTATES: dict[tuple[str, int], np.ndarray] = {
    ("Z", 0): np.array([1.0, 0.0], dtype=complex),
    ("Z", 1): np.array([0.0, 1.0], dtype=complex),
    ("X", 0): np.array([_S, _S], dtype=complex),          # |+>
    ("X", 1): np.array([_S, -_S], dtype=complex),         # |->
    ("Y", 0): np.array([_S, 1j * _S], dtype=complex),     # |+i>
    ("Y", 1): np.array([_S, -1j * _S], dtype=complex),    # |-i>
}

BASES: tuple[str, ...] = ("X", "Y", "Z")

# Human-readable labels for the UI.
BASIS_LABEL = {
    "X": "Pauli-X  (|+>, |->)",
    "Y": "Pauli-Y  (|+i>, |-i>)",
    "Z": "Pauli-Z  (|0>, |1>)",
}
BIT_LABEL = {
    ("Z", 0): "|0>", ("Z", 1): "|1>",
    ("X", 0): "|+>", ("X", 1): "|->",
    ("Y", 0): "|+i>", ("Y", 1): "|-i>",
}


def eigenstate(basis: str, bit: int) -> np.ndarray:
    """State vector for the (basis, bit) Pauli eigenstate."""
    return EIGENSTATES[(basis, int(bit))].copy()


def label(basis: str, bit: int) -> str:
    """Dirac label, e.g. ('X', 0) -> '|+>'."""
    return BIT_LABEL.get((basis, int(bit)), f"|{basis}{int(bit)}>")


def random_eigenstate(rng: np.random.Generator) -> tuple[str, int, np.ndarray]:
    """Draw a uniformly random Pauli eigenstate.

    Returns (basis, bit, vector).  Consumes exactly two RNG draws so the
    signature generator and the verification replay stay bit-for-bit
    consistent for the same seed.
    """
    basis = BASES[int(rng.integers(0, len(BASES)))]
    bit = int(rng.integers(0, 2))
    return basis, bit, eigenstate(basis, bit)


def measure_in_basis(
    state: np.ndarray,
    basis: str,
    rng: np.random.Generator,
    flip: float = 0.0,
) -> int:
    """Projectively measure `state` in the given Pauli `basis`.

    Born rule against the two eigenstates of that basis, then an optional
    symmetric bit-flip `flip` (channel / attack noise).  Returns the
    eigenvalue bit (0 for +1, 1 for -1).
    """
    e0 = EIGENSTATES[(basis, 0)]
    e1 = EIGENSTATES[(basis, 1)]
    p0 = float(abs(np.vdot(e0, state)) ** 2)
    p1 = float(abs(np.vdot(e1, state)) ** 2)
    total = p0 + p1
    p0 = p0 / total if total else 0.5
    bit = 0 if rng.random() < p0 else 1
    if flip > 0.0 and rng.random() < flip:
        bit ^= 1
    return bit


def check_outcome(
    committed_basis: str,
    committed_bit: int,
    measurement_basis: str,
    observed_bit: int,
) -> bool | None:
    """Compare Bob's measurement against the committed eigenstate.

    Returns True/False when the bases match (a real check), or None when the
    bases differ (the qubit is discarded -- no information can be extracted).
    """
    if measurement_basis != committed_basis:
        return None
    return observed_bit == int(committed_bit)


def expected_checks(n_qubits: int) -> int:
    """Expected number of checked qubits when Bob's basis is random.

    Each of the (n_qubits - 1) non-reference qubits matches Alice's basis
    with probability 1/3.
    """
    return max(1, int(round((max(2, int(n_qubits)) - 1) / len(BASES))))
