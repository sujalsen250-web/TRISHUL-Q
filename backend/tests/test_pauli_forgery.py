"""v8 scientific-core tests: Pauli eigenstates + forgery-probability engine."""
from __future__ import annotations

import numpy as np

from backend.detection import forgery
from backend.quantum import pauli_eigenstates as pe


def test_six_eigenstates_present_and_normalised():
    assert len(pe.EIGENSTATES) == 6
    for vec in pe.EIGENSTATES.values():
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-9


def test_eigenstate_labels():
    assert pe.label("Z", 0) == "|0>"
    assert pe.label("X", 0) == "|+>"
    assert pe.label("Y", 1) == "|-i>"


def test_measurement_is_deterministic_in_matching_basis():
    rng = np.random.default_rng(3)
    for basis in pe.BASES:
        for bit in (0, 1):
            state = pe.eigenstate(basis, bit)
            observed = [pe.measure_in_basis(state, basis, rng) for _ in range(50)]
            assert set(observed) == {bit}


def test_check_outcome_discards_on_basis_mismatch():
    assert pe.check_outcome("Z", 1, "Z", 1) is True
    assert pe.check_outcome("Z", 1, "Z", 0) is False
    assert pe.check_outcome("Z", 1, "X", 0) is None


def test_expected_checks_third_of_qubits():
    assert pe.expected_checks(48) == round(47 / 3)
    assert pe.expected_checks(4) >= 1


def test_closed_form_p_forge_is_no_cloning_bound():
    assert abs(forgery.closed_form_p_forge(0) - 1.0) < 1e-12
    assert abs(forgery.closed_form_p_forge(10) - 0.5 ** 10) < 1e-12


def test_p_forge_curve_monotone_decreasing():
    curve = forgery.p_forge_curve()
    vals = [p["p_forge"] for p in curve]
    assert vals == sorted(vals, reverse=True)
    assert vals[-1] < vals[0]


def test_honest_acceptance_near_one():
    res = forgery.honest_acceptance(48, trials=300)
    assert res["p_honest"] >= 0.98


def test_attack_suite_covers_eight_attacks():
    suite = forgery.attack_suite(48, trials=40)
    assert len(suite["attacks"]) == 8
    names = {a["attack"] for a in suite["attacks"]}
    assert "unauthorized_verification" in names
    assert "basis_guessing" in names


def test_structural_attacks_always_detected():
    for attack in forgery.STRUCTURAL_ATTACKS:
        mc = forgery.monte_carlo(attack, 48, 0.5, trials=60)
        assert mc["detection_rate"] == 1.0


def test_basis_guessing_detection_high():
    mc = forgery.monte_carlo("basis_guessing", 48, 1.0, trials=200)
    assert mc["detection_rate"] > 0.9
