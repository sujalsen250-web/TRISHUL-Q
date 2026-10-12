"""Quantum Random Number Generator built on Qiskit.

The QDS framework sources its randomness from a REAL quantum process
(simulated on the Qiskit Aer stabilizer simulator): each qubit is put in
equal superposition with a Hadamard gate and then measured in the
computational basis.  Before measurement the outcome is genuinely
undetermined -- |0> and |1> each occur with probability exactly 1/2 -- so
the measured bit stream is quantum randomness, not a classical PRNG.

v7 ROBUSTNESS RULES (this module must NEVER break, hang or crash the
server, no matter what state the local qiskit install is in):
  * every qiskit run happens in a SEPARATE SHORT-LIVED SUBPROCESS with a
    hard timeout -- a broken/crashing Aer install can never take the
    server down with it (a segfault only kills that child process);
  * if qiskit is missing, fails, times out or crashes ONCE, the module
    permanently switches to the OS CSPRNG for the rest of the session;
  * qiskit is an OPTIONAL install (requirements-quantum.txt) -- the
    framework always works without it.
"""
from __future__ import annotations

import subprocess
import sys

import secrets as _secrets
import threading

_POOL_TARGET_BITS = 2048        # bits per refill (~85 signatures per run)
_MAX_CIRCUIT_QUBITS = 64       # qubits per single circuit
_FIRST_TIMEOUT_S = 20.0        # first attempt: includes COLD qiskit import
_TIMEOUT_S = 10.0              # later runs (OS file cache helps a little)

_LOCK = threading.Lock()
_POOL: str = ""                # cached '0'/'1' bits
_BACKEND_NAME: str | None = None
_QISKIT_STATE: str = "untested"   # untested | ok | disabled(<reason>)

# The child program: generate n quantum-random bits with H + measure and
# print them as a hex string. Kept self-contained on purpose.
# Output protocol:  line 1 = hex bits, line 2 = "backend:<label>".
# If QDS_IBM_BACKEND is set (e.g. "ibm_brisbane") it tries IBM Quantum cloud
# first (requires qiskit-ibm-runtime + saved account) and silently falls
# back to the local Aer simulator on any problem.
_CHILD_CODE = r'''
import os, sys
n = int(sys.argv[1])
try:
    from qiskit import QuantumCircuit
except Exception:
    sys.exit(3)  # qiskit not installed

def gen_cloud(service, name, n):
    backend = service.backend(name)
    from qiskit import transpile
    from qiskit_ibm_runtime import SamplerV2
    out = []
    remaining = n
    while remaining > 0:
        k = min(remaining, 64)
        qc = QuantumCircuit(k, k)
        qc.h(range(k))
        qc.measure(range(k), range(k))
        job = SamplerV2(mode=backend).run([transpile(qc, backend)], shots=1)
        out.append(next(iter(job.result()[0].data.c.values()))["bitstring"])
        remaining -= k
    return "".join(out), "ibm cloud: " + name

def gen_local(n):
    from qiskit_aer import AerSimulator
    sim = AerSimulator(method="stabilizer", max_parallel_threads=1)
    out = []
    remaining = n
    while remaining > 0:
        k = min(remaining, 64)
        qc = QuantumCircuit(k, k)
        qc.h(range(k))
        qc.measure(range(k), range(k))
        counts = sim.run(qc, shots=1, memory=True).result().get_memory()
        out.append(counts[0])
        remaining -= k
    return "".join(out), "qiskit-aer local simulator (H + measure)"

label = ""
cloud = os.environ.get("QDS_IBM_BACKEND", "").strip()
bits = None
if cloud:
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
        bits, label = gen_cloud(QiskitRuntimeService(), cloud, n)
    except Exception as exc:
        sys.stderr.write("cloud backend unavailable (%r); using local Aer\n" % (exc,))
        bits = None
if bits is None:
    bits, label = gen_local(n)
sys.stdout.write(format(int(bits, 2), "0{}x".format((n + 3) // 4)))
sys.stdout.write("\nbackend:" + label)
'''


def _qiskit_bits_subprocess(n: int) -> tuple[str | None, str]:
    """Run the QRNG child process. Returns (bits, status); bits is None on
    any failure. Crash/timeout of the child cannot harm the server."""
    timeout = _FIRST_TIMEOUT_S if _QISKIT_STATE == "untested" else _TIMEOUT_S
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD_CODE, str(n)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout", ""
    except Exception as exc:                          # pragma: no cover
        return None, f"spawn failed ({type(exc).__name__})", ""
    if proc.returncode == 3:
        return None, "not installed", ""
    if proc.returncode != 0:
        why = (proc.stderr or "").strip().splitlines()
        reason = why[-1][:80] if why else f"exit {proc.returncode}"
        return None, "crashed: " + reason, ""
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    bits_hex = lines[0] if lines else ""
    backend_label = ""
    for ln in lines[1:]:
        if ln.startswith("backend:"):
            backend_label = ln[len("backend:"):].strip()
    try:
        bits = format(int(bits_hex, 16), "0{}b".format(n))
    except ValueError:
        return None, "bad output", ""
    if len(bits) != n:
        return None, "short output", backend_label
    return bits, "ok", backend_label


def _fallback_bits(n: int) -> str:
    """n random bits from the OS CSPRNG."""
    return format(_secrets.randbits(n), "0{}b".format(n))


def _refill(need: int) -> None:
    """Top the pool up (called under lock). Never raises, never hangs,
    never crashes the process."""
    global _POOL, _BACKEND_NAME, _QISKIT_STATE
    want = max(need, _POOL_TARGET_BITS)
    if _QISKIT_STATE != "ok":
        if _QISKIT_STATE.startswith("disabled"):
            # permanently on fallback for this session
            _BACKEND_NAME = "OS entropy fallback (" + _QISKIT_STATE[9:] + ")"
            _POOL += _fallback_bits(want)
            return
        # untested -> try qiskit exactly once (in a child process)
        bits, status, label = _qiskit_bits_subprocess(want)
        if bits is not None:
            _QISKIT_STATE = "ok"
            _BACKEND_NAME = label or "qiskit-aer local simulator (H + measure)"
            _POOL += bits
            return
        _QISKIT_STATE = "disabled: qiskit " + status
        _BACKEND_NAME = "OS entropy fallback (qiskit " + status + ")"
        _POOL += _fallback_bits(want)
        return
    # qiskit was working -- keep using it, fall back permanently if it dies
    bits, status, label = _qiskit_bits_subprocess(want)
    if bits is not None:
        if label:
            _BACKEND_NAME = label
        _POOL += bits
        return
    _QISKIT_STATE = "disabled: qiskit " + status + " (switched mid-run)"
    _BACKEND_NAME = "OS entropy fallback (qiskit " + status + ")"
    _POOL += _fallback_bits(want)


def random_bits(n: int) -> str:
    """Return n quantum-random bits as a '0'/'1' string. Never fails."""
    global _POOL
    n = max(0, int(n))
    if n == 0:
        return ""
    with _LOCK:
        if len(_POOL) < n:
            _refill(n - len(_POOL) + _POOL_TARGET_BITS)
        bits = _POOL[:n]
        _POOL = _POOL[n:]
    return bits


def random_hex(n_nibbles: int) -> str:
    """Return a hex string of n_nibbles quantum-random characters."""
    n = max(1, int(n_nibbles))
    bits = random_bits(n * 4)
    return format(int(bits, 2), "0{}x".format(n))


def backend_name() -> str:
    """Human-readable name of the live randomness source (lazy init)."""
    if _BACKEND_NAME is None:
        random_bits(4)
    return _BACKEND_NAME or "unknown"


def health_check(n_bits: int = 4096) -> dict:
    """Chi-square uniformity test (scipy.stats.chisquare) on a fresh
    quantum sample -- the standard randomness health check for the live
    QRNG source. A p-value above 0.01 means the bit stream is
    statistically indistinguishable from uniform.
    """
    from scipy.stats import chisquare   # imported lazily: scipy is heavy

    n_bits = min(max(int(n_bits), 256), 16384)
    bits = random_bits(n_bits)
    ones = bits.count("1")
    zeros = n_bits - ones
    stat, p = chisquare([zeros, ones])
    return {
        "backend": backend_name(),
        "n_bits": n_bits,
        "ones": ones,
        "zeros": zeros,
        "ratio": round(ones / n_bits, 4),
        "chi2": round(float(stat), 4),
        "p_value": round(float(p), 4),
        "uniform_at_1pct": bool(float(p) > 0.01),
        "test": "scipy.stats.chisquare (Pearson, 1 df)",
    }


def warmup_async() -> None:
    """Background warm-up so the first signature is not delayed and a bad
    Aer install is detected (safely, in a child process) before the first
    request needs it."""
    def _w():
        try:
            random_bits(_POOL_TARGET_BITS)
            print(f"  QRNG ready: {backend_name()}")
        except Exception:                                # pragma: no cover
            print("  QRNG warmup failed (will fall back at first use)")
    t = threading.Thread(target=_w, daemon=True, name="qds-qrng-warmup")
    t.start()
