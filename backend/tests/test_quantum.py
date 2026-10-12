"""Quantum engine tests -- teleportation, Pauli, Bell states, QEC."""
from __future__ import annotations

import numpy as np

from backend.quantum.bell_states import BELL_STATES
from backend.quantum import pauli as P
from backend.quantum.qec import logical_error_rate, transmit
from backend.quantum.qubit import random_qubit
from backend.quantum.teleportation import teleport


def test_all_bell_pairs_teleport_with_unit_fidelity():
    rng = np.random.default_rng(7)
    for name in BELL_STATES:
        psi = random_qubit(rng)
        result = teleport(psi, name, rng)
        assert result["fidelity_after_correction"] > 0.999999


def test_pauli_correction_table():
    assert P.correction_for_bits("00") == "I"
    assert P.correction_for_bits("01") == "X"
    assert P.correction_for_bits("10") == "Z"
    assert P.correction_for_bits("11") == "XZ"


def test_pauli_apply_operation_involution():
    state = np.array([0.6, 0.8], dtype=complex)
    assert np.allclose(P.apply_operation(P.apply_operation(state, "X"), "X"), state)
    assert np.allclose(P.apply_operation(P.apply_operation(state, "Z"), "Z"), state)


def test_qec_logical_error_is_cubic():
    assert abs(logical_error_rate(0.1) - 0.028) < 1e-9
    assert logical_error_rate(0.5) == 0.5
    assert logical_error_rate(0.0) == 0.0


def test_qec_transmit_reduces_errors():
    rng = np.random.default_rng(1)
    _, stats = transmit([1, 0, 1, 1, 0] * 40, 0.05, rng)
    assert stats["logical_error_rate"] <= stats["physical_error_rate"]
