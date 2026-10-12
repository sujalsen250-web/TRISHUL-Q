"""In-memory rate limiting / brute-force protection for TRISHUL-Q.

A small sliding-window limiter used to protect login and password-reset
endpoints. Keyed by bucket + identity (usually client IP, sometimes email).
Process-local and intentionally dependency-free.
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_HITS: dict[tuple[str, str], list[float]] = {}


def _prune(times: list[float], window: float, now: float) -> list[float]:
    return [t for t in times if now - t < window]


def allow(bucket: str, key: str, limit: int, window: int) -> tuple[bool, int]:
    """Record an attempt and report whether it is allowed.

    Returns (allowed, retry_after_seconds). When the caller is over the limit
    the attempt is NOT recorded again (so the window drains naturally).
    """
    now = time.time()
    k = (bucket, key or "-")
    with _LOCK:
        times = _prune(_HITS.get(k, []), window, now)
        if len(times) >= limit:
            retry = int(window - (now - times[0])) + 1
            _HITS[k] = times
            return False, max(1, retry)
        times.append(now)
        _HITS[k] = times
        return True, 0


def reset(bucket: str, key: str) -> None:
    with _LOCK:
        _HITS.pop((bucket, key or "-"), None)


def clear_all() -> None:
    with _LOCK:
        _HITS.clear()
