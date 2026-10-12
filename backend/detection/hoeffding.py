"""Hoeffding-based adaptive statistical bounds (deterministic, no ML).

Why
---
The deviation D measured from n projective measurements always contains
SAMPLING NOISE, even for a perfectly legitimate message: with n finite,
|P_obs - P_exp| can never be exactly zero.  If the classification
thresholds ignore this noise floor, a small sample can trigger a FALSE
ALARM -- exactly the "rigid threshold" risk identified in the SIH
feasibility analysis.

Hoeffding's inequality (1963) gives a rigorous, distribution-free bound:

    P( |P_obs - P_exp| >= eps ) <= 2 * exp(-2 n eps^2)

so with confidence 1 - alpha,

    eps(n, alpha) = sqrt( ln(2/alpha) / (2 n) )

is the maximum deviation that pure chance can produce from an honest
quantum source.  The QDS decision engine therefore widens the
classification thresholds to at least this noise floor:

    t_suspicious_eff = max(t_suspicious, eps(n, alpha))
    t_threat_eff    = max(t_threat,    t_suspicious_eff)

More measurements  ->  tighter bound  ->  sharper detection.
Fewer measurements  ->  wider bound   ->  no false alarms.

This is the "Adaptive 3-Sigma buffer" of the SIH proposal in its exact
mathematical form (the z=3 one-sided confidence of the Gaussian
approximation corresponds to alpha ~ 1.35e-3, which is the default here).
"""
from __future__ import annotations

import math

# False-alarm probability budget (one-sided z=3 => alpha = 1 - Phi(3)).
DEFAULT_ALPHA = 0.00135


def hoeffding_epsilon(n: int, alpha: float = DEFAULT_ALPHA) -> float:
    """Maximum deviation attributable to pure sampling noise.

    With probability >= 1 - alpha, an honest source measured n times
    cannot deviate more than this from the expected distribution.
    """
    n = max(1, int(n))
    alpha = min(max(alpha, 1e-12), 0.5)
    return math.sqrt(math.log(2.0 / alpha) / (2.0 * n))


def adaptive_thresholds(
    t_suspicious: float,
    t_threat: float,
    n_measurements: int,
    alpha: float = DEFAULT_ALPHA,
) -> tuple[float, float, float]:
    """Widen the base thresholds past the Hoeffding noise floor.

    Returns (t_suspicious_eff, t_threat_eff, epsilon).  Never narrows
    the operator's thresholds -- only protects against false positives.
    """
    eps = hoeffding_epsilon(n_measurements, alpha)
    t_susp_eff = max(t_suspicious, eps)
    t_threat_eff = max(t_threat, t_susp_eff)
    return t_susp_eff, t_threat_eff, eps
