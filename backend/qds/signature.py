"""Teleportation-based Quantum Digital Signature generation.

A signature binds a message to:
  * its SHA-256 hash,
  * a sender identity (username + device IP),
  * a nonce and timestamp,
  * a seeded simulation of N quantum teleportation rounds (Bell pair,
    measurement outcomes, Pauli corrections),
  * an HMAC (server-side secret) over all signature metadata.

The seed is derived deterministically from the message hash + nonce, so the
receiver can replay the exact teleportation sequence and confirm that the
measurement record it received was genuinely produced for this message.
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import time
from datetime import datetime, timezone

import numpy as np

from .. import db as dbm
from ..config import SIGNATURE_TTL_SECONDS, get_or_create_secret
from ..quantum.bell_states import BELL_STATES
from ..quantum.pauli_eigenstates import (EIGENSTATES, label as eigen_label,
                                         random_eigenstate)
from ..quantum.qrng import (backend_name as qrng_backend, random_bits,
                            random_hex)
from ..quantum.qubit import fmt_state, probabilities, random_qubit
from ..quantum.teleportation import teleport

_SECRET = get_or_create_secret()

# v9 -- length of the quantum salt (extra random bits appended to the stream).
SALT_BITS = 32


def _salt_hash(bits: str) -> str:
    """Hash of the decoded quantum-salt bit-string (binds it into the MAC)."""
    return hashlib.sha256(("qsalt:" + bits).encode()).hexdigest()


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _derive_seed(message_hash: str, nonce: str, sender: str) -> int:
    material = f"{message_hash}:{nonce}:{sender}".encode()
    digest = hmac_mod.new(_SECRET, material, hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") % (2 ** 62)   # fits SQLite INTEGER


def _canonical_mac_fields(sig: dict) -> str:
    return "|".join([
        sig["signature_id"], sig["message_hash"], sig["nonce"],
        sig["sender_username"], sig["bell_state"], str(sig["seed"]),
        str(sig["n_qubits"]), sig["teleport_digest"],
    ])


def compute_mac(signature_id, message_hash, nonce, sender, bell_state, seed,
               n_qubits, teleport_digest, salt_hash: str = "") -> str:
    fields = [signature_id, message_hash, nonce, sender, bell_state,
              str(seed), str(n_qubits), teleport_digest]
    if salt_hash:                      # only v9+ signatures carry a salt
        fields.append(salt_hash)
    return hmac_mod.new(_SECRET, "|".join(fields).encode(),
                        hashlib.sha256).hexdigest()


REFERENCE_STATE = np.array([np.sqrt(0.95), np.sqrt(0.05)], dtype=complex)


def generate_signature(message_hash: str, sender_username: str,
                       sender_ip: str | None, bell_state: str = "PHI_PLUS",
                       n_qubits: int = 32) -> dict:
    """Simulate the QDS signature for a given message hash.

    Qubit #0 of every signature is a deterministic REFERENCE STATE
    |psi_ref> = sqrt(0.95)|0> + sqrt(0.05)|1>; the receiver monitors the
    quantum channel by measuring it and comparing against the expected
    95%/5% distribution (see measurement.py).

    v8 -- every OTHER qubit is prepared in a random Pauli eigenstate
    (|0>, |1>, |+>, |->, |+i>, |-i>).  Its (basis, eigenvalue) is committed
    in the signature metadata and re-measured by the receiver in a random
    Pauli basis (see quantum/pauli_eigenstates.py + qds/verification.py).
    """
    t0 = time.perf_counter()

    if bell_state not in BELL_STATES:
        raise ValueError(f"Unknown Bell state: {bell_state}")
    # Nonce comes from the Qiskit QRNG (genuinely quantum randomness).
    nonce = random_hex(6).upper()
    seed = _derive_seed(message_hash, nonce, sender_username)
    rng = np.random.default_rng(seed)

    teleports = []
    p0_sum = 0.0
    for i in range(n_qubits):
        if i == 0:
            # deterministic reference qubit (Z-basis deviation anchor)
            psi = REFERENCE_STATE.copy()
            basis, eigen_bit, is_ref = "Z", 0, True
        else:
            # v8: every other qubit is a random Pauli eigenstate
            basis, eigen_bit, psi = random_eigenstate(rng)
            is_ref = False
        result = teleport(psi, bell_state, rng)
        p0, _ = probabilities(psi)
        p0_sum += p0
        teleports.append({
            "alpha": [round(float(psi[0].real), 4), round(float(psi[0].imag), 4)],
            "beta": [round(float(psi[1].real), 4), round(float(psi[1].imag), 4)],
            "bits": result["bits"],
            "pauli": result["applied_correction"],
            "fidelity": result["fidelity_after_correction"],
            "basis": basis,
            "eigen_bit": eigen_bit,
            "reference": is_ref,
        })

    # v9 -- QUANTUM SALT -----------------------------------------------------
    # Append SALT_BITS extra qubits whose deterministic Z-basis eigenvalues
    # carry a QRNG-generated random bit-string. The receiver DECODES this
    # bit-string straight out of the transmitted qubit record. Its hash is
    # folded into the signature MAC, so the salt is tamper-evident exactly
    # like a cryptographic salt: altering or stripping it breaks the MAC.
    salt_bits = random_bits(SALT_BITS)
    for bit in salt_bits:
        psi = EIGENSTATES[("Z", int(bit))]
        result = teleport(psi, bell_state, rng)
        teleports.append({
            "alpha": [round(float(psi[0].real), 4), round(float(psi[0].imag), 4)],
            "beta": [round(float(psi[1].real), 4), round(float(psi[1].imag), 4)],
            "bits": result["bits"],
            "pauli": result["applied_correction"],
            "fidelity": result["fidelity_after_correction"],
            "basis": "Z",
            "eigen_bit": int(bit),
            "reference": False,
            "salt": True,
        })
    salt_hash = _salt_hash(salt_bits)

    # expected distribution = reference qubit measurement (stable 95/5 anchor)
    expected = {"0": 0.95, "1": 0.05}

    # sequential signature id: QDS-<year>-<counter>
    year = datetime.now(timezone.utc).year
    count = dbm.query_one("SELECT COUNT(*) AS c FROM signatures")["c"] + 1
    signature_id = f"QDS-{year}-{count:04d}"

    teleport_digest = hashlib.sha256(
        json.dumps([[t["bits"], t["pauli"], t["fidelity"]] for t in teleports]).encode()
    ).hexdigest()
    mac = compute_mac(signature_id, message_hash, nonce, sender_username,
                      bell_state, seed, n_qubits, teleport_digest, salt_hash)

    generation_time_ms = (time.perf_counter() - t0) * 1000
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dbm.execute(
        """INSERT INTO signatures(signature_id, message_id, message_hash, bell_state,
               quantum_state, seed, n_qubits, n_measurements, measurement_result,
               pauli_operation, expected_distribution, teleports, mac, sender_username,
               sender_ip, nonce, verification_status, created_at, generation_time_ms)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (signature_id, None, message_hash, bell_state,
         fmt_state(np.array([complex(teleports[0]["alpha"][0], teleports[0]["alpha"][1]),
                             complex(teleports[0]["beta"][0], teleports[0]["beta"][1])], dtype=complex)),
         seed, n_qubits, 0, teleports[0]["bits"],
         teleports[0]["pauli"], json.dumps(expected), json.dumps(teleports), mac,
         sender_username, sender_ip, nonce, "PENDING", now, generation_time_ms),
    )
    dbm.execute(
        "INSERT INTO performance_metrics(operation, duration_ms, ref_id, created_at) "
        "VALUES('signature_generation',?,?,?)",
        (generation_time_ms, signature_id, now),
    )

    return {
        "signature_id": signature_id,
        "message_hash": message_hash,
        "nonce": nonce,
        "qrng_source": qrng_backend(),
        "valid_for_seconds": SIGNATURE_TTL_SECONDS,
        "bell_state": bell_state,
        "bell_symbol": BELL_STATES[bell_state]["symbol"],
        "quantum_state": fmt_state(np.array([complex(*teleports[0]["alpha"]), complex(*teleports[0]["beta"])], dtype=complex)),
        "n_qubits": n_qubits,
        "seed": seed,
        "expected_distribution": expected,
        "teleport_preview": teleports[:6],
        "pauli_key_preview": [
            {"qubit": i + 1, "basis": t["basis"],
             "state": eigen_label(t["basis"], t["eigen_bit"])}
            for i, t in enumerate(teleports)
            if not t["reference"] and not t.get("salt")
        ][:12],
        "pauli_basis_counts": {
            b: sum(1 for t in teleports
                   if not t["reference"] and not t.get("salt") and t["basis"] == b)
            for b in ("X", "Y", "Z")
        },
        "quantum_salt": {
            "bits": salt_bits,
            "n_bits": SALT_BITS,
            "salt_hash": salt_hash,
            "note": ("QRNG salt bits appended to the qubit stream; the receiver "
                     "decodes them and checks the MAC-bound hash."),
        },
        "generation_time_ms": round(generation_time_ms, 2),
    }
