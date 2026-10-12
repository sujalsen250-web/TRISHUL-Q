"""Quantum Error Correction: 3-qubit bit-flip repetition code.

Motivation (SIH feasibility: "NISQ-Era Hardware Noise")
------------------------------------------------------
Real quantum channels and simulators inject bit-flip errors with some
probability p (decoherence, gate error, noisy eavesdropping).  The QDS
framework protects every transmitted signature qubit with the classic
3-qubit repetition code:

    |psi> = a|0> + b|1>   --encode-->   a|000> + b|111>

A single bit flip on any one of the three physical qubits is detected
and corrected by a majority vote (syndrome measurement + recovery), so
the logical error probability collapses to the probability of >= 2 flips:

    P_L(p) = C(3,2) p^2 (1-p) + p^3 = 3 p^2 - 2 p^3

e.g. p = 0.10  ->  P_L = 0.028  (3.6x suppression)
     p = 0.20  ->  P_L = 0.104  (~2x suppression, quadratic regime)

The verification pipeline routes the adversarial/noisy channel
flip_epsilon through this code, so the statistical deviation D reflects
the CORRECTED (logical) error rate, not the raw physical one.  A mild
eavesdropper whose noise would have tripped the threshold is absorbed
by QEC, while a strong attacker (large p) still breaks through --
exactly the "absorb hardware noise, keep security" trade-off promised in
the SIH proposal.

Everything here is deterministic NumPy linear algebra -- no ML, no
guesswork.
"""
from __future__ import annotations

import numpy as np


def logical_error_rate(p: float) -> float:
    """P(failure of the 3-qubit majority-vote code) given physical flip prob p."""
    p = min(max(float(p), 0.0), 1.0)
    return 3.0 * p * p - 2.0 * p * p * p


def encode(bit: int) -> np.ndarray:
    """Encode one logical bit into a 3-qubit repetition codeword (basis)."""
    b = int(bit) & 1
    return np.array([b, b, b], dtype=np.int8)


def channel(codeword: np.ndarray, p: float, rng: np.random.Generator) -> np.ndarray:
    """Depolarising-style bit-flip channel: each physical qubit flips with prob p."""
    flips = rng.random(len(codeword)) < p
    return (codeword ^ flips.astype(np.int8)).astype(np.int8)


def syndrome(codeword: np.ndarray) -> np.ndarray:
    """Parity checks z1 = b0^b1, z2 = b1^b2 (stabilizer measurement)."""
    return np.array([codeword[0] ^ codeword[1],
                     codeword[1] ^ codeword[2]], dtype=np.int8)


def correct(codeword: np.ndarray) -> np.ndarray:
    """Majority-vote recovery using the syndrome (classical feedback)."""
    z1, z2 = syndrome(codeword)
    out = codeword.copy()
    if z1 and not z2:            # first qubit flipped
        out[0] ^= 1
    elif z1 and z2:              # second qubit flipped
        out[1] ^= 1
    elif z2 and not z1:          # third qubit flipped
        out[2] ^= 1
    return out


def decode(codeword: np.ndarray) -> int:
    """Logical readout = majority of the corrected codeword."""
    return int(np.count_nonzero(codeword) >= 2)


def transmit(bits, p: float, rng: np.random.Generator) -> tuple[list[int], dict]:
    """Send a bit string through the QEC-protected channel.

    Returns (received_bits, stats).  Stats include the empirical
    physical and logical error rates actually observed in this run.
    """
    p = min(max(float(p), 0.0), 1.0)
    received: list[int] = []
    physical_flips = 0
    logical_flips = 0
    total = 0
    for bit in bits:
        total += 1
        b = int(bit) & 1
        cw = channel(encode(b), p, rng)
        corrected = correct(cw)
        out = decode(corrected)
        physical_flips += int(np.count_nonzero(cw != encode(b)))
        logical_flips += int(out != b)
        received.append(out)
    n = max(1, total)
    return received, {
        "code": "3-qubit bit-flip repetition (majority vote)",
        "physical_error_rate": round(physical_flips / (3 * n), 4),
        "logical_error_rate": round(logical_flips / n, 4),
        "theoretical_logical_rate": round(logical_error_rate(p), 4),
    }


def protection_curve(points: int = 21) -> list[dict]:
    """Physical vs logical error rate over p in [0, 0.5] -- for the UI."""
    points = max(2, int(points))
    out = []
    for i in range(points):
        p = 0.5 * i / (points - 1)
        pl = logical_error_rate(p)
        out.append({
            "physical": round(p, 3),
            "logical": round(pl, 5),
            "suppression": round(p / pl, 2) if pl > 0 else None,
        })
    return out
