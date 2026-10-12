# TRISHUL-Q — Security model & attack coverage

**Honest scope note.** TRISHUL-Q is a *software simulation* of a quantum
digital-signature (QDS) protocol — exact linear algebra in NumPy. It does **not**
run on quantum hardware and does **not** claim unconditional
(information-theoretic) security. No system is "attack-proof"; below is what is
actually enforced and where the limits are.

## Protections enforced

| Attack | Defence |
|---|---|
| Message tampering | SHA-256 of the message (+ attachment) re-computed by the receiver |
| Signature forgery / metadata tampering | HMAC-SHA256 (server secret) over signature id, message hash, nonce, sender, bell state, seed, n_qubits, teleport digest **and salt hash** |
| Impersonation | Claimed sender must equal the signature owner **and** the session user **and** the source IP bound at signing |
| Replay | One-time nonce (`used_nonces`) + signature TTL (60 s) |
| Basis-guessing / forged eigenvalues | Random Pauli X/Y/Z basis checks; per-basis QBER threshold |
| Quantum-channel manipulation | Reference-qubit 95/5 deviation + 3-qubit QEC + Hoeffding-widened thresholds |
| Salt stripping / alteration | Salt hash bound into the MAC → any change fails verification |
| Unauthorised verification | Only the addressed receiver (or an admin) may verify; otherwise an `UNAUTHORIZED_VERIFICATION` event is raised |

## Limits (be aware)

- HMAC security depends on the server secret (`data/secret.key`) staying private.
- Sender-IP binding can reject legitimate users behind changing NAT / proxies.
- Thresholds are tuned to avoid false positives; a very low-rate attacker may
  land in **SUSPICIOUS** rather than **REJECT**.
- The "quantum" layer is simulated; security is **computational**, not physical.
- Email delivery depends on a correctly configured SMTP account.
