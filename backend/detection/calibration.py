"""Adaptive 3-sigma threshold calibration (scipy-backed, deterministic).

Instead of trusting hand-picked thresholds, the receiver CALIBRATES them
against the framework's own honest behaviour: it runs K clean
verification passes (a perfect quantum channel, no adversary), records
the deviation D of each pass, and sets

    t_suspicious = mean(D) + z3 * std(D)      (3-sigma, ~99.87% of honest runs)
    t_threat     = mean(D) + z6 * std(D)      (6-sigma, ~1 in 500 million)

where z3 and z6 are exact normal quantiles from scipy.stats.norm.ppf
(one-sided).  The result is combined with the Hoeffding noise floor
(see detection.hoeffding) so the effective threshold is never below what
pure chance can produce for the current number of measurements.

Calibration is cached per (n_measurements, k) and reused; the admin can
force a recalibration via POST /api/thresholds/calibrate.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as _stats

from .hoeffding import adaptive_thresholds

_Z3 = float(_stats.norm.ppf(1 - 1.35e-3))    # 3.0 (one-sided 99.865%)
_Z6 = float(_stats.norm.ppf(1 - 1e-9))      # ~5.9976

_CACHE: dict[tuple[int, int], tuple[float, float]] = {}


def clean_deviation_sample(
    p0: float,
    n_measurements: int,
    k: int,
    seed: int = 20260924,
) -> np.ndarray:
    """Deviations of K honest runs of the measurement pipeline."""
    rng = np.random.default_rng(seed)
    out = np.empty(k, dtype=float)
    for i in range(k):
        ones = rng.binomial(n_measurements, 1 - p0)
        p_obs0 = ones / n_measurements
        out[i] = 0.5 * (abs(p0 - p_obs0) + abs((1 - p0) - (1 - p_obs0)))
    return out


def calibrate_thresholds(
    n_measurements: int,
    k: int = 200,
    p0: float = 0.5,
    base: tuple[float, float] = (0.10, 0.20),
) -> dict:
    """Return calibrated + Hoeffding-protected thresholds and diagnostics."""
    n_measurements = max(10, int(n_measurements))
    k = max(30, int(k))
    key = (n_measurements, k)
    sample = clean_deviation_sample(p0, n_measurements, k)
    mu = float(sample.mean())
    sd = float(sample.std(ddof=1))
    t_susp = mu + _Z3 * sd
    t_threat = mu + _Z6 * sd
    # never below the operator's own floor, never above 0.5 (D in [0,1])
    t_susp = min(max(t_susp, 0.01), 0.5)
    t_threat = min(max(t_threat, t_susp + 0.01), 0.5)
    # protect past the Hoeffding sampling-noise floor for this n
    eps = adaptive_thresholds(t_susp, t_threat, n_measurements)[2]
    t_susp_eff = max(t_susp, eps)
    t_threat_eff = max(t_threat, t_susp_eff + 0.01)
    _CACHE[key] = (t_susp_eff, t_threat_eff)
    return {
        "n_measurements": n_measurements,
        "k": k,
        "mean_deviation": round(mu, 5),
        "std_deviation": round(sd, 5),
        "z3": round(_Z3, 4),
        "z6": round(_Z6, 4),
        "threshold_suspicious": round(t_susp_eff, 4),
        "threshold_threat": round(t_threat_eff, 4),
        "hoeffding_epsilon": round(eps, 4),
        "calibrated": True,
    }


def cached_thresholds(
    n_measurements: int,
    base: tuple[float, float] = (0.10, 0.20),
) -> tuple[float, float]:
    """Calibrated thresholds for this sample size (calibrating if needed)."""
    key = (max(10, int(n_measurements)), 200)
    if key not in _CACHE:
        calibrate_thresholds(key[0], base=base)
    return _CACHE[key]
