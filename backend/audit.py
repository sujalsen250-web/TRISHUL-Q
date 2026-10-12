"""Audit logging for TRISHUL-Q.

Security-sensitive operations are recorded in the ``audit_logs`` table with the
actor, action, target, result, IP and timestamp.  Never stores secrets.
"""
from __future__ import annotations

from . import db as dbm

# Canonical action names (kept stable for querying / reporting).
ADMIN_CREATED = "Admin Created"
ADMIN_ACTIVATED = "Admin Activated"
ADMIN_DEACTIVATED = "Admin Deactivated"
ADMIN_REMOVED = "Admin Removed"
ADMIN_PASSWORD_RESET = "Admin Password Reset"
WELCOME_EMAIL_RESENT = "Welcome Email Resent"
PASSWORD_RESET_REQUESTED = "Password Reset Requested"
PASSWORD_RESET_COMPLETED = "Password Reset Completed"
PASSWORD_CHANGED = "Password Changed"
GOOGLE_LOGIN = "Google Login"
EMAIL_LOGIN = "Email Login"
FAILED_LOGIN = "Failed Login"
LOGOUT = "Logout"
SENDER_CREATED = "Sender Created"
SENDER_ACTIVATED = "Sender Activated"
SENDER_DEACTIVATED = "Sender Deactivated"
SUPERADMIN_LOGIN = "Super Admin Login"


def log(action: str, *, actor: str | None = None, target: str | None = None,
        result: str = "success", ip: str | None = None,
        detail: str | None = None) -> None:
    """Write one audit record. Never raises (auditing must not break flows)."""
    try:
        dbm.execute(
            "INSERT INTO audit_logs(actor, action, target, result, ip, detail, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (actor, action, target, result, ip, detail, dbm.utcnow()),
        )
    except Exception:
        pass


def recent(limit: int = 200) -> list[dict]:
    limit = max(1, min(1000, int(limit)))
    return dbm.query("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))


def for_action(action: str, limit: int = 200) -> list[dict]:
    return dbm.query("SELECT * FROM audit_logs WHERE action=? ORDER BY id DESC LIMIT ?",
                     (action, max(1, min(1000, int(limit)))))
