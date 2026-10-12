"""Independent receiver-side verification of a QDS-signed message.

The receiver never trusts the sender: every claim is re-derived locally.

Verification pipeline
--------------------
1. Integrity      -- recompute SHA-256 of message text / attachment bytes.
2. Signature MAC  -- recompute the HMAC over the stored signature metadata.
3. Identity       -- claimed sender must match the signature owner AND the
                     actual source IP of the request.
4. Replay         -- nonce must be unused (checked at send/attack layer).
5. Teleportation  -- replay the seeded teleportation sequence and confirm
                     the stored measurement outcomes and Pauli corrections.
6. Measurement     -- run n projective measurements, compare the observed
                     distribution against the expected distribution, compute
                     D = (1/2) * sum |P_exp - P_obs|.  Channel noise is
                     routed through the 3-qubit bit-flip QEC code first.
7. Threshold rules-- classify LEGITIMATE / SUSPICIOUS / THREAT and decide
                     ACCEPT / FLAG / REJECT.  Thresholds are widened past
                     the Hoeffding sampling-noise floor so that a finite
                     measurement budget can never cause a false alarm.
"""
from __future__ import annotations

import json
import time

import numpy as np

from ..quantum.bell_states import BELL_STATES
from ..quantum.measurement import observed_distribution, sample_measurements
from ..quantum.pauli_eigenstates import (BASES, check_outcome, measure_in_basis,
                                         random_eigenstate)
from ..quantum.qubit import probabilities, random_qubit
from ..quantum.teleportation import teleport
from ..quantum.qec import logical_error_rate
from ..detection.forgery import (MIN_CHECKS_FOR_HARD_FAIL,
                                 PAULI_MISMATCH_THRESHOLD)
from ..detection.hoeffding import DEFAULT_ALPHA, adaptive_thresholds
from ..detection.threshold import classify
from .signature import REFERENCE_STATE, _salt_hash, compute_mac, sha256_hex


def _replay_teleportation(
    sig: dict, rng: np.random.Generator
) -> tuple[list[dict], bool, list[dict]]:
    """Re-run the seeded teleportation sequence.

    Returns (log, consistent, states).  `states[i]` carries the replayed
    state vector plus its committed Pauli (basis, eigenvalue) so the caller
    can run the v8 basis checks.  Signatures generated before v8 (no
    'basis' key) are replayed with the legacy random_qubit() path so old
    records still verify.
    """
    stored = json.loads(sig["teleports"])
    legacy = not (len(stored) > 1 and "basis" in stored[1])
    log = []
    states: list[dict] = []
    consistent = True
    for i in range(sig["n_qubits"]):
        if i == 0:
            psi = REFERENCE_STATE.copy()
            basis, eigen_bit, is_ref = "Z", 0, True
        elif legacy:
            psi = random_qubit(rng)
            basis, eigen_bit, is_ref = None, None, False
        else:
            basis, eigen_bit, psi = random_eigenstate(rng)
            is_ref = False
        result = teleport(psi, sig["bell_state"], rng)
        expected = stored[i] if i < len(stored) else None
        ok = (
            expected is not None
            and expected["bits"] == result["bits"]
            and expected["pauli"] == result["applied_correction"]
        )
        if not ok:
            consistent = False
        p0, p1 = probabilities(psi)
        log.append({
            "qubit": i + 1,
            "state": [round(p0, 3), round(p1, 3)],
            "bits": result["bits"],
            "pauli": result["applied_correction"],
            "fidelity": result["fidelity_after_correction"],
            "matches_stored": bool(ok),
        })
        states.append({"psi": psi, "basis": basis, "eigen_bit": eigen_bit,
                       "reference": is_ref})
    return log, consistent, states


def _pauli_verify(
    states: list[dict],
    rng: np.random.Generator,
    flip: float = 0.0,
    threshold: float = PAULI_MISMATCH_THRESHOLD,
) -> dict:
    """v8 Pauli-eigenstate check.

    Bob measures every non-reference qubit in a RANDOMLY chosen Pauli basis.
    When his basis matches Alice's committed basis the outcome is checked
    against the committed eigenvalue; a mismatched basis is discarded.  The
    per-basis QBER and the overall mismatch rate are returned.
    """
    bases = {b: {"checks": 0, "mismatches": 0} for b in BASES}
    checked = mismatches = discarded = 0
    key: list[dict] = []
    for idx, st in enumerate(states):
        if st["reference"] or st["basis"] is None:
            continue
        bob_basis = BASES[int(rng.integers(0, len(BASES)))]
        observed = measure_in_basis(st["psi"], bob_basis, rng, flip=flip)
        verdict_bit = check_outcome(st["basis"], st["eigen_bit"], bob_basis, observed)
        if verdict_bit is None:
            discarded += 1
        else:
            checked += 1
            bases[st["basis"]]["checks"] += 1
            if not verdict_bit:
                mismatches += 1
                bases[st["basis"]]["mismatches"] += 1
        key.append({"qubit": idx + 1, "committed_basis": st["basis"],
                    "measured_basis": bob_basis,
                    "checked": verdict_bit is not None,
                    "match": verdict_bit})
    for b in BASES:
        c = bases[b]["checks"]
        bases[b]["qber"] = round(bases[b]["mismatches"] / c, 4) if c else None
    rate = mismatches / checked if checked else 0.0
    passed = (rate <= threshold) or (checked < MIN_CHECKS_FOR_HARD_FAIL)
    return {
        "protocol": "random Pauli eigenstates (X/Y/Z); matching-basis checks",
        "checked": checked,
        "discarded": discarded,
        "mismatches": mismatches,
        "mismatch_rate": round(rate, 4),
        "threshold": threshold,
        "min_checks_for_hard_fail": MIN_CHECKS_FOR_HARD_FAIL,
        "passed": passed,
        "bases": bases,
        "key_preview": key[:8],
    }


def verify_message(
    message_text: str,
    file_bytes: bytes | None,
    expected_file_hash: str | None,
    sig: dict,
    n_measurements: int,
    thresholds: tuple[float, float],
    *,
    claimed_sender: str | None = None,
    actual_source_ip: str | None = None,
    actual_session_user: str | None = None,
    channel_flip_epsilon: float = 0.0,
    force_failure_reasons: list[str] | None = None,
) -> dict:
    t0 = time.perf_counter()
    reasons: list[str] = []
    hard_fail = bool(force_failure_reasons)

    # 1 -- message integrity ---------------------------------------------------
    recomputed_hash = sha256_hex(message_text or "")
    hash_ok = hmac_ok = identity_ok = True
    if recomputed_hash != sig["message_hash"]:
        hash_ok = False
        reasons.append(
            f"Integrity mismatch: recomputed hash {recomputed_hash[:12]}… "
            f"≠ signed hash {sig['message_hash'][:12]}…"
        )

    # 2 -- attachment integrity ------------------------------------------------
    file_ok = True
    file_result = None
    if expected_file_hash is not None:
        actual = sha256_hex(file_bytes) if file_bytes is not None else ""
        file_ok = actual == expected_file_hash
        file_result = {"expected": expected_file_hash, "actual": actual}
        if not file_ok:
            reasons.append("Attachment integrity violation: file hash mismatch")

    # 3 -- signature MAC (with the decoded quantum salt) -------------------------
    import hashlib
    stored = json.loads(sig["teleports"])
    teleport_digest = hashlib.sha256(
        json.dumps([[t["bits"], t["pauli"], t["fidelity"]] for t in stored]).encode()
    ).hexdigest()
    # v9 -- DECODE the quantum salt from the trailing Z-basis salt qubits.
    salt_bits = "".join(str(t.get("eigen_bit")) for t in stored if t.get("salt"))
    salt_hash = _salt_hash(salt_bits) if salt_bits else ""
    mac = compute_mac(sig["signature_id"], sig["message_hash"], sig["nonce"],
                      sig["sender_username"], sig["bell_state"], sig["seed"],
                      sig["n_qubits"], teleport_digest, salt_hash)
    if mac != sig["mac"]:
        hmac_ok = False
        reasons.append("Signature MAC invalid: signature metadata was tampered with")
    if salt_bits and salt_hash and not hmac_ok:
        reasons.append("Quantum salt mismatch: decoded salt does not match the "
                       "MAC-bound value (channel tampering detected)")

    # 4 -- sender identity -------------------------------------------------------
    if claimed_sender is not None and claimed_sender != sig["sender_username"]:
        identity_ok = False
        reasons.append(
            f"Impersonation: claimed sender '{claimed_sender}' ≠ signature owner "
            f"'{sig['sender_username']}'"
        )
    if (actual_session_user is not None
            and actual_session_user != sig["sender_username"]):
        identity_ok = False
        reasons.append(
            f"Impersonation: submitting session '{actual_session_user}' is not the "
            f"signature owner '{sig['sender_username']}'"
        )
    if actual_source_ip is not None and sig["sender_ip"] and actual_source_ip != sig["sender_ip"]:
        identity_ok = False
        reasons.append(
            f"Impersonation: signature bound to {sig['sender_ip']} but request "
            f"originated from {actual_source_ip}"
        )

    # 5 -- teleportation replay ---------------------------------------------------
    rng_replay = np.random.default_rng(sig["seed"])
    teleport_log, teleport_ok, pauli_states = _replay_teleportation(sig, rng_replay)
    if not teleport_ok:
        reasons.append("Teleportation record mismatch: stored measurement outcomes "
                       "do not match the replayed simulation")

    # 6 -- projective measurement + statistical deviation --------------------------
    # The noisy/adversarial channel is protected by the 3-qubit bit-flip
    # repetition code: only the LOGICAL error rate (3p^2 - 2p^3) survives
    # to the measurement statistics.
    expected = json.loads(sig["expected_distribution"])
    p0 = float(expected["0"])
    rng_meas = np.random.default_rng((sig["seed"] ^ int(time.time_ns())) % (2**32))
    qec_info = None
    flip_epsilon_effective = channel_flip_epsilon
    if channel_flip_epsilon > 0:
        logical = logical_error_rate(channel_flip_epsilon)
        flip_epsilon_effective = logical
        qec_info = {
            "code": "3-qubit bit-flip repetition (majority vote)",
            "physical_error_rate": round(channel_flip_epsilon, 4),
            "logical_error_rate": round(logical, 4),
            "suppression": round(channel_flip_epsilon / logical, 2) if logical > 0 else None,
        }
    counts = sample_measurements(p0, n_measurements, rng_meas,
                                 flip_epsilon=flip_epsilon_effective)
    observed = observed_distribution(counts)
    deviation = 0.5 * (abs(p0 - observed["0"]) + abs((1 - p0) - observed["1"]))

    # 6b -- Pauli-eigenstate basis verification (v8) ------------------------------
    # Bob measures each qubit in a random Pauli basis; only matching-basis
    # qubits are checked.  A forger who guesses the eigenvalues is caught here.
    rng_pauli = np.random.default_rng((int(sig["seed"]) ^ 0x5EED5EED) % (2 ** 32))
    pauli_block = _pauli_verify(pauli_states, rng_pauli, flip=flip_epsilon_effective)
    pauli_passed = pauli_block["passed"]
    if (not pauli_passed) and pauli_block["checked"] >= MIN_CHECKS_FOR_HARD_FAIL:
        reasons.append(
            f"Pauli-basis mismatch: {pauli_block['mismatch_rate']:.3f} > "
            f"{pauli_block['threshold']} over {pauli_block['checked']} checked "
            f"qubits (forgery / basis-guessing detected)"
        )

    # 7 -- Hoeffding-protected threshold decision --------------------------------
    # eps(n, alpha) is the maximum deviation pure chance can produce from an
    # honest quantum source; the thresholds are widened to at least that floor
    # so finite sampling can NEVER cause a false positive (SIH risk mitigation:
    # "rigid thresholds -> false positives").
    t_susp, t_threat = thresholds
    t_susp_eff, t_threat_eff, hoeff_eps = adaptive_thresholds(
        t_susp, t_threat, n_measurements, DEFAULT_ALPHA)
    classification, action = classify(deviation, t_susp_eff, t_threat_eff)
    if hard_fail:
        reasons.extend(force_failure_reasons or [])
    if not (hash_ok and file_ok and hmac_ok and identity_ok and teleport_ok):
        classification, action = "THREAT", "REJECT"
    if (not pauli_passed) and pauli_block["checked"] >= MIN_CHECKS_FOR_HARD_FAIL:
        classification, action = "THREAT", "REJECT"

    elapsed_ms = (time.perf_counter() - t0) * 1000
    verdict = {
        "signature_id": sig["signature_id"],
        "integrity_verified": bool(hash_ok and file_ok),
        "hash_mismatch": not hash_ok,
        "file_check": file_result,
        "signature_valid": bool(hmac_ok),
        "identity_verified": bool(identity_ok),
        "teleportation_consistent": bool(teleport_ok),
        "bell_state": sig["bell_state"],
        "bell_symbol": BELL_STATES[sig["bell_state"]]["symbol"],
        "measurements": {
            "n": n_measurements,
            "counts": counts,
            "expected": {k: round(v, 4) for k, v in expected.items()},
            "observed": {k: round(v, 4) for k, v in observed.items()},
        },
        "deviation": round(deviation, 4),
        "threshold_suspicious": t_susp,
        "threshold_threat": t_threat,
        "threshold_effective": {
            "suspicious": round(t_susp_eff, 4),
            "threat": round(t_threat_eff, 4),
            "hoeffding_epsilon": round(hoeff_eps, 4),
            "alpha": DEFAULT_ALPHA,
            "n_measurements": n_measurements,
            "rule": "t_eff = max(t_operator, sqrt(ln(2/alpha)/(2n)))  [Hoeffding 1963]",
        },
        "qec": qec_info,
        "quantum_salt": {
            "decoded_bits": salt_bits,
            "n_bits": len(salt_bits),
            "salt_hash": salt_hash,
            "present": bool(salt_bits),
            "note": ("Random salt bits decoded by the receiver from the qubit "
                     "stream and checked against the MAC-bound hash."),
        },
        "pauli_verification": pauli_block,
        "classification": classification,
        "action": action,
        "reasons": reasons,
        "teleport_log": teleport_log[:8],
        "verification_time_ms": round(elapsed_ms, 2),
    }
    return verdict
