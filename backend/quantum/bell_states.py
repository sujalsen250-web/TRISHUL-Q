"""The four maximally entangled Bell states.

    |PHI+> = (|00> + |11>)/sqrt(2)
    |PHI-> = (|00> - |11>)/sqrt(2)
    |PSI+> = (|01> + |10>)/sqrt(2)
    |PSI-> = (|01> - |10>)/sqrt(2)

Each Bell state is associated with the classical two-bit outcome of a
Bell-basis measurement, following the standard teleportation convention:
    PHI+ -> 00, PSI+ -> 01, PHI- -> 10, PSI- -> 11
"""
from __future__ import annotations

import numpy as np

_S = 1.0 / np.sqrt(2.0)

BELL_STATES: dict[str, dict] = {
    "PHI_PLUS": {
        "vector": np.array([_S, 0, 0, _S], dtype=complex),
        "symbol": "Φ+",
        "latex": "|Φ+⟩ = (|00⟩+|11⟩)/√2",
        "bits": "00",
    },
    "PHI_MINUS": {
        "vector": np.array([_S, 0, 0, -_S], dtype=complex),
        "symbol": "Φ−",
        "latex": "|Φ−⟩ = (|00⟩−|11⟩)/√2",
        "bits": "10",
    },
    "PSI_PLUS": {
        "vector": np.array([0, _S, _S, 0], dtype=complex),
        "symbol": "Ψ+",
        "latex": "|Ψ+⟩ = (|01⟩+|10⟩)/√2",
        "bits": "01",
    },
    "PSI_MINUS": {
        "vector": np.array([0, _S, -_S, 0], dtype=complex),
        "symbol": "Ψ−",
        "latex": "|Ψ−⟩ = (|01⟩−|10⟩)/√2",
        "bits": "11",
    },
}

DEFAULT_BELL = "PHI_PLUS"


def bell_vector(name: str) -> np.ndarray:
    return BELL_STATES[name]["vector"]


def bell_options() -> list[dict]:
    """Metadata for the UI dropdown."""
    return [
        {"key": key, "symbol": info["symbol"], "latex": info["latex"]}
        for key, info in BELL_STATES.items()
    ]
