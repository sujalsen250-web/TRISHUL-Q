"""Projective measurement simulation and statistical deviation.

Mathematical model
------------------
For a single qubit |psi> = alpha|0> + beta|1>, projective measurement in the
computational basis yields 0 with probability P0 = |alpha|^2 and 1 with
probability P1 = |beta|^2.  We sample N independent shots and compare the
observed relative frequencies with the expected probabilities.

Deviation (normalised total variation distance):

    D = (1/2) * sum_i |P_expected_i - P_observed_i|      (D in [0, 1])
"""
from __future__ import annotations

import numpy as np


def sample_measurements(p0: float, n: int, rng: np.random.Generator,
                        flip_epsilon: float = 0.0) -> dict:
    """Sample n projective measurements of a qubit with P(|0>) = p0.

    `flip_epsilon` models a noisy/adversarial channel that flips a |0>
    outcome to |1> with that probability (asymmetric bit-flip / relaxation
    model used for channel-manipulation attack simulation).
    """
    n = max(1, int(n))
    draws = rng.random(n)
    zeros = draws < p0
    if flip_epsilon > 0:
        flip_mask = rng.random(n) < flip_epsilon
        zeros = zeros & ~flip_mask          # 0 -> 1 flips only
    count0 = int(zeros.sum())
    return {"zeros": count0, "ones": n - count0, "n": n}


def observed_distribution(counts: dict) -> dict:
    n = counts["n"]
    return {"0": counts["zeros"] / n, "1": counts["ones"] / n}


def deviation(expected: dict, observed: dict) -> float:
    """D = (1/2) * sum_i |P_exp_i - P_obs_i|, averaged over outcome labels."""
    keys = set(expected) | set(observed)
    return 0.5 * sum(abs(expected.get(k, 0.0) - observed.get(k, 0.0)) for k in keys)


def expected_vs_observed(expected: dict, observed: dict) -> dict:
    return {
        "expected": {k: round(v, 4) for k, v in expected.items()},
        "observed": {k: round(v, 4) for k, v in observed.items()},
        "deviation": round(deviation(expected, observed), 4),
    }
