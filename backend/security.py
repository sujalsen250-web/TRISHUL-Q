"""Small security utilities for TRISHUL-Q.

* Built-in random password generator (used by the Super Admin panel when an
  admin account is created from an approved registration request).
* Password-strength estimation (advisory, no ML).
"""
from __future__ import annotations

import secrets
import string

_LOWER = string.ascii_lowercase
_UPPER = string.ascii_uppercase
_DIGITS = string.digits
_SYMBOLS = "!@#$%^&*-_=+?"


def generate_password(length: int = 14) -> str:
    """Cryptographically-random password with at least one of every class."""
    length = max(10, min(64, int(length)))
    pools = [_LOWER, _UPPER, _DIGITS, _SYMBOLS]
    while True:
        chars = [secrets.choice(p) for p in pools]
        alphabet = "".join(pools)
        chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
        secrets.SystemRandom().shuffle(chars)
        candidate = "".join(chars)
        if (any(c in _LOWER for c in candidate)
                and any(c in _UPPER for c in candidate)
                and any(c in _DIGITS for c in candidate)
                and any(c in _SYMBOLS for c in candidate)):
            return candidate


def password_strength(password: str) -> dict:
    """Advisory strength score in [0, 4] (entropy-class based, no ML)."""
    p = password or ""
    score = 0
    if len(p) >= 8:
        score += 1
    if len(p) >= 12:
        score += 1
    if any(c in _LOWER for c in p) and any(c in _UPPER for c in p):
        score += 1
    if any(c in _DIGITS for c in p) and any(c in _SYMBOLS for c in p):
        score += 1
    return {"score": score, "label": ["very weak", "weak", "fair", "strong",
                                      "very strong"][score]}
