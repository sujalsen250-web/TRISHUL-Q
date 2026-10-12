"""Threshold-based threat decision rules (deterministic, no ML).

    D <= t_suspicious            -> LEGITIMATE / ACCEPT
    t_suspicious < D <= t_threat -> SUSPICIOUS  / FLAG
    D > t_threat                 -> THREAT      / REJECT
"""
from __future__ import annotations


def classify(deviation: float, t_suspicious: float, t_threat: float) -> tuple[str, str]:
    if deviation <= t_suspicious:
        return "LEGITIMATE", "ACCEPT"
    if deviation <= t_threat:
        return "SUSPICIOUS", "FLAG"
    return "THREAT", "REJECT"


def decision_table(t_suspicious: float, t_threat: float) -> list[dict]:
    """Human-readable decision rules for the admin UI."""
    return [
        {"rule": f"D ≤ {t_suspicious:.2f}", "classification": "LEGITIMATE", "action": "ACCEPT"},
        {"rule": f"{t_suspicious:.2f} < D ≤ {t_threat:.2f}", "classification": "SUSPICIOUS", "action": "FLAG"},
        {"rule": f"D > {t_threat:.2f}", "classification": "THREAT", "action": "REJECT"},
    ]
