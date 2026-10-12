"""Deterministic statistical analysis (no machine learning).

Deviation model
---------------
D = (1/2) * sum_i |P_expected_i - P_observed_i|   in [0, 1]

All numbers are computed from live simulations at runtime -- nothing is
hardcoded per attack type.
"""
from __future__ import annotations


def total_deviation(expected: dict, observed: dict) -> float:
    keys = set(expected) | set(observed)
    return 0.5 * sum(abs(expected.get(k, 0.0) - observed.get(k, 0.0)) for k in keys)


def summarize(expected: dict, observed: dict) -> dict:
    d = total_deviation(expected, observed)
    return {
        "expected": {k: round(v, 4) for k, v in expected.items()},
        "observed": {k: round(v, 4) for k, v in observed.items()},
        "deviation": round(d, 4),
    }
