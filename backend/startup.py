"""Startup validation + status banner for TRISHUL-Q.

Verifies PostgreSQL connectivity, schema, authentication tables and the
Super Admin configuration, then prints a clear status report. In production a
failure to reach PostgreSQL is fatal (no silent SQLite fallback).
"""
from __future__ import annotations

from . import config
from . import db as dbm


def _qiskit_available() -> bool:
    try:
        import qiskit  # noqa: F401
        import qiskit_aer  # noqa: F401
        return True
    except Exception:
        return False


def status() -> dict:
    db_status = dbm.database_status()
    sa = None
    auth_ready = False
    if db_status.get("connected") and not db_status.get("missing_tables"):
        try:
            sa = dbm.query_one("SELECT username, is_active FROM users WHERE role='superadmin'")
            auth_ready = sa is not None
        except Exception:
            auth_ready = False
    return {
        "database": db_status,
        "superadmin_configured": sa is not None,
        "superadmin_active": bool(sa and sa.get("is_active")),
        "auth_ready": auth_ready,
        "google_oauth": config.google_configured(),
        "smtp": config.smtp_configured(),
        "qiskit": _qiskit_available(),
        "env": config.APP_ENV,
    }


def banner_lines() -> list[str]:
    s = status()
    db = s["database"]
    lines = [
        "=" * 62,
        f"  {config.APP_NAME}  v{config.VERSION}",
        f"  {config.APP_FULL_NAME}",
        "=" * 62,
        f"  Database          : {'PostgreSQL' if db.get('dialect') == 'postgresql' else 'SQLite (development)'}",
        f"  Database Status   : {'CONNECTED' if db.get('connected') else 'NOT CONNECTED'}",
        f"  Schema            : {'READY' if db.get('ready') else 'INCOMPLETE'}"
        + (f" (missing: {', '.join(db.get('missing_tables', []))})"
           if db.get("missing_tables") else ""),
        f"  Authentication    : {'READY' if s['auth_ready'] else 'NOT READY (super-admin missing)'}",
        f"  Google OAuth      : {'CONFIGURED' if s['google_oauth'] else 'NOT CONFIGURED'}",
        f"  SMTP              : {'CONFIGURED' if s['smtp'] else 'NOT CONFIGURED'}",
        f"  Qiskit            : {'AVAILABLE' if s['qiskit'] else 'NOT INSTALLED (OS-entropy fallback)'}",
        f"  Quantum Simulator : READY",
        f"  Environment       : {config.APP_ENV}",
        "=" * 62,
        f"  Public app        : {config.LOCAL_USER_URL}",
        f"  Super Admin panel : {config.LOCAL_SUPERADMIN_URL}   (localhost only)",
        "=" * 62,
    ]
    return lines


def print_banner() -> None:
    for line in banner_lines():
        print(line)


def fatal_db_error() -> str | None:
    """Return an error string when the database is not usable."""
    db = dbm.database_status()
    if not db.get("connected"):
        return (f"Database connection failed ({db.get('dialect')}): "
                f"{db.get('error', 'unknown error')}")
    if db.get("missing_tables"):
        return f"Database schema incomplete; missing tables: {db['missing_tables']}"
    return None
