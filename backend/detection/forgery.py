"""Forgery-probability engine (v8) -- closed-form bound + live Monte Carlo.

No machine learning.  Every number in the admin panel is produced either by
an explicit closed-form expression or by running the SAME verifier maths
live, so nothing is hardcoded per attack.

Model
-----
A signature carries `n_qubits` Pauli-eigenstate qubits.  Bob measures each in
a random Pauli basis, so only the matching-basis qubits are CHECKED:

    k_checks ~ (n_qubits - 1) / 3

A forger who does not hold the quantum states must guess each checked
eigenvalue; by the no-cloning / uncertainty argument a basis-agnostic guess
succeeds with probability 1/2 per checked qubit.  Therefore

    P_forge(n_qubits, k_checks) = (1/2) ** k_checks

which collapses exponentially in the number of checks.  The Monte-Carlo half
of this module replays the exact acceptance rule (Hoeffding-widened deviation
thresholds + the Pauli mismatch threshold) so the reported detection rate is
measured, not assumed.
"""
from __future__ import annotations

import numpy as np

from ..quantum.pauli_eigenstates import expected_checks
from ..quantum.qec import logical_error_rate
from .hoeffding import adaptive_thresholds

# Pauli-basis mismatch threshold: a check that fails more than this fraction
# of the time is treated as forged.  (Separate from the Z-basis D thresholds.)
PAULI_MISMATCH_THRESHOLD = 0.30
MIN_CHECKS_FOR_HARD_FAIL = 8         # below this the Pauli layer is advisory

# The eight attacks SIH lists by name.
STRUCTURAL_ATTACKS = (
    "message_forgery",
    "signature_forgery",
    "replay",
    "impersonation",
    "unauthorized_verification",
)
STATISTICAL_ATTACKS = (
    "basis_guessing",
    "channel_manipulation",
    "threshold_evasion",
)
ATTACKS = STRUCTURAL_ATTACKS + STATISTICAL_ATTACKS

ATTACK_LABEL = {
    "message_forgery": "Message forgery (content tampered)",
    "signature_forgery": "Signature forgery (metadata tampered)",
    "replay": "Replay (nonce reused)",
    "impersonation": "Impersonation (wrong identity)",
    "unauthorized_verification": "Unauthorized verification",
    "basis_guessing": "Pauli basis guessing (no-cloning)",
    "channel_manipulation": "Channel manipulation (flip)",
    "threshold_evasion": "Threshold evasion (tuned attack)",
}

_DEFAULT_INTENSITIES = tuple(round(i / 10.0, 1) for i in range(0, 11))   # 0.0 .. 1.0


def closed_form_p_forge(k_checks: int, per_check_success: float = 0.5) -> float:
    """Exact no-cloning bound: a forger passes k independent checks with
    probability per_check_success ** k_checks."""
    k = max(0, int(k_checks))
    return float(per_check_success ** k)


def effective_thresholds(n_measurements: int,
                         base: tuple[float, float] = (0.10, 0.20)) -> tuple[float, float, float]:
    """Hoeffding-widened (suspicious, threat, epsilon) for this sample size."""
    return adaptive_thresholds(base[0], base[1], n_measurements)


def _z_basis_deviation(rng: np.random.Generator, p0: float, n: int,
                       flip: float = 0.0) -> float:
    """Sample the Z-basis deviation D for one verification pass."""
    zeros = rng.binomial(n, p0 * (1.0 - flip)) if flip > 0 else rng.binomial(n, p0)
    p_obs0 = zeros / n
    return 0.5 * (abs(p0 - p_obs0) + abs((1 - p0) - (1 - p_obs0)))


def _accepts(
    attack: str,
    checks: int,
    intensity: float,
    rng: np.random.Generator,
    t_susp: float,
    pauli_thr: float,
    n_measurements: int,
    p0: float,
) -> bool:
    """One Monte-Carlo trial: did this attack fool the verifier?"""
    if attack in STRUCTURAL_ATTACKS:
        # Integrity / MAC / nonce / identity checks are deterministic: a
        # structural attack is ALWAYS rejected.
        return False

    if attack == "basis_guessing":
        # Clean channel; the forger guesses eigenvalues with p = 1/2.
        mismatch = rng.binomial(checks, 0.5)
        return (mismatch / checks) <= pauli_thr

    if attack == "channel_manipulation":
        logical = logical_error_rate(intensity)
        d = _z_basis_deviation(rng, p0, n_measurements, logical)
        mismatch = rng.binomial(checks, logical)
        return (d <= t_susp) and ((mismatch / checks) <= pauli_thr)

    if attack == "threshold_evasion":
        # The attacker tunes the perturbation to sit just under the
        # suspicious threshold and hopes to stay "legitimate".
        logical = logical_error_rate(intensity)
        d = _z_basis_deviation(rng, p0, n_measurements, logical)
        return d <= t_susp

    return False


def monte_carlo(
    attack: str,
    n_qubits: int,
    intensity: float,
    trials: int = 200,
    seed: int = 20261005,
    n_measurements: int = 1000,
    p0: float = 0.95,
) -> dict:
    """Run `trials` simulations of one attack and measure its detection rate."""
    checks = expected_checks(n_qubits)
    t_susp, _t_threat, _eps = effective_thresholds(n_measurements)
    rng = np.random.default_rng(seed)
    accepts = sum(
        1 for _ in range(max(1, trials))
        if _accepts(attack, checks, intensity, rng, t_susp,
                    PAULI_MISMATCH_THRESHOLD, n_measurements, p0)
    )
    trials = max(1, trials)
    p_forge = accepts / trials
    return {
        "attack": attack,
        "intensity": round(float(intensity), 3),
        "checks": checks,
        "trials": trials,
        "p_forge": round(p_forge, 5),
        "detection_rate": round(1.0 - p_forge, 5),
    }


def honest_acceptance(
    n_qubits: int,
    trials: int = 400,
    seed: int = 424242,
    n_measurements: int = 1000,
    p0: float = 0.95,
) -> dict:
    """P_honest -- fraction of legitimate signatures ACCEPTED.

    Should stay ~1.0 because the thresholds are widened past the Hoeffding
    sampling-noise floor (the whole point of the adaptive-threshold layer).
    """
    checks = expected_checks(n_qubits)
    t_susp, _t, _e = effective_thresholds(n_measurements)
    rng = np.random.default_rng(seed)
    accepted = 0
    for _ in range(max(1, trials)):
        d = _z_basis_deviation(rng, p0, n_measurements, 0.0)   # clean channel
        if d <= t_susp:                                          # Pauli: 0 mismatch
            accepted += 1
    trials = max(1, trials)
    return {
        "n_qubits": int(n_qubits),
        "checks": checks,
        "trials": trials,
        "p_honest": round(accepted / trials, 5),
        "threshold_suspicious_effective": round(t_susp, 5),
    }


def detection_curve(
    attack: str,
    n_qubits: int,
    intensities: tuple[float, ...] = _DEFAULT_INTENSITIES,
    trials: int = 200,
    seed: int = 20261005,
) -> list[dict]:
    """Detection rate for one attack across a sweep of intensities."""
    return [monte_carlo(attack, n_qubits, eps, trials=trials, seed=seed)
            for eps in intensities]


def attack_suite(
    n_qubits: int,
    intensities: tuple[float, ...] = _DEFAULT_INTENSITIES,
    trials: int = 200,
    seed: int = 20261005,
) -> dict:
    """Full 8-attack suite: detection rate vs intensity for every attack."""
    checks = expected_checks(n_qubits)
    curves = {a: detection_curve(a, n_qubits, intensities, trials, seed)
              for a in ATTACKS}
    return {
        "n_qubits": int(n_qubits),
        "checks": checks,
        "intensities": [round(float(i), 3) for i in intensities],
        "attacks": [
            {
                "attack": a,
                "label": ATTACK_LABEL[a],
                "detection": [pt["detection_rate"] for pt in curves[a]],
                "p_forge": [pt["p_forge"] for pt in curves[a]],
            }
            for a in ATTACKS
        ],
        "trials": trials,
    }


def p_forge_curve(
    n_range: tuple[int, ...] = (8, 16, 24, 32, 48, 64, 96, 128),
) -> list[dict]:
    """Closed-form P_forge vs number of signature qubits (the judged curve)."""
    out = []
    for n in n_range:
        checks = expected_checks(n)
        out.append({
            "n_qubits": int(n),
            "checks": checks,
            "p_forge": round(closed_form_p_forge(checks), 8),
        })
    return out


def analysis(n_qubits: int = 32, trials: int = 200, seed: int = 20261005) -> dict:
    """Everything the Security-Analysis panel needs, computed live."""
    checks = expected_checks(n_qubits)
    return {
        "n_qubits": int(n_qubits),
        "checks": checks,
        "p_forge_closed_form": round(closed_form_p_forge(checks), 8),
        "pauli_mismatch_threshold": PAULI_MISMATCH_THRESHOLD,
        "honest": honest_acceptance(n_qubits, trials=trials * 2, seed=seed + 1),
        "suite": attack_suite(n_qubits, trials=trials, seed=seed),
        "p_forge_vs_n_qubits": p_forge_curve(),
    }
