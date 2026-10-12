"""Authentication, password hashing, sessions, roles & capabilities.

TRISHUL-Q roles (three security roles):

    superadmin  -- separate, simpler panel; LOCALHOST ONLY (server-enforced)
    admin       -- online; created by the Super Admin; manages Senders
    user        -- Sender / Receiver; capabilities 'send' / 'receive'

* Login is EMAIL + PASSWORD (username is also accepted as a fallback id).
* Google OAuth users are always normal users -- never admin/superadmin.
* Password-reset tokens are single-use, hashed at rest and expire.
* Admins created with a generated password must change it on first login.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request

from . import db as dbm
from . import security
from .config import (CAPABILITIES, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME,
                     DEFAULT_SUPERADMIN_PASSWORD, LOCAL_HOSTNAMES,
                     PASSWORD_RESET_TTL_SECONDS, SESSION_TTL_SECONDS,
                     SEED_DEFAULT_ADMIN, SUPERADMIN_USERNAME)

_PBKDF2_ITERATIONS = 200_000

DEFAULT_SECURITY_QUESTION = "What is this framework called? (in capitals)"


# ------------------------------------------------------------- passwords -----
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                                 _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt,
                                 _PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _hash_answer(answer: str) -> str:
    normalized = " ".join((answer or "").strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------- capabilities ------
def get_capabilities(user: dict) -> list[str]:
    if user.get("role") in ("admin", "superadmin"):
        return ["send", "receive"]
    try:
        caps = json.loads(user.get("capabilities") or "[]")
    except (TypeError, ValueError):
        caps = []
    return [c for c in caps if c in CAPABILITIES]


def has_capability(user: dict, capability: str) -> bool:
    return capability in get_capabilities(user)


def require_capability(capability: str):
    if capability == "admin":
        return require_role("admin")

    def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] in ("admin", "superadmin") or has_capability(user, capability):
            return user
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized: this action requires the '{capability}' capability",
        )

    return dep


# --------------------------------------------------------- localhost check ---
def is_local_request(request: Request) -> bool:
    allowed_hosts = {"testserver", "testclient"} | set(LOCAL_HOSTNAMES)
    host = (request.headers.get("host") or "").split(":")[0].lower()
    client = (request.client.host if request.client else "")
    return host in allowed_hosts and client in (
        "127.0.0.1", "::1", "localhost", "testclient")


def require_role(*roles: str):
    def dep(request: Request, user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Unauthorized: this endpoint requires role in {list(roles)}",
            )
        if "superadmin" in roles and user["role"] == "superadmin" \
                and not is_local_request(request):
            raise HTTPException(status_code=403,
                                detail="Super Admin access is restricted to localhost")
        return user

    return dep


# ----------------------------------------------------- persistent sessions ---
def create_session(username: str, role: str, ip: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now.timestamp() + SESSION_TTL_SECONDS
    dbm.execute(
        "INSERT INTO sessions(token, username, role, ip, created_at, expires_at) "
        "VALUES(?,?,?,?,?,?)",
        (token, username, role, ip, now.isoformat(timespec="seconds"),
         datetime.fromtimestamp(expires, timezone.utc).isoformat(timespec="seconds")),
    )
    return token


def destroy_session(token: str) -> None:
    if token:
        dbm.execute("DELETE FROM sessions WHERE token=?", (token,))


def destroy_user_sessions(username: str) -> None:
    dbm.execute("DELETE FROM sessions WHERE username=?", (username,))


def get_session(token: str) -> dict | None:
    if not token:
        return None
    row = dbm.query_one("SELECT * FROM sessions WHERE token=?", (token,))
    if not row:
        return None
    try:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            dbm.execute("DELETE FROM sessions WHERE token=?", (token,))
            return None
    except (TypeError, ValueError):
        dbm.execute("DELETE FROM sessions WHERE token=?", (token,))
        return None
    return {"username": row["username"], "role": row["role"], "ip": row["ip"]}


def purge_expired_sessions() -> None:
    dbm.execute("DELETE FROM sessions WHERE expires_at < ?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),))


def get_current_user(request: Request) -> dict:
    token = request.cookies.get("trishul_session", "")
    sess = get_session(token)
    if not sess:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = dbm.query_one("SELECT * FROM users WHERE username=?", (sess["username"],))
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    if not user.get("is_active", 1):
        raise HTTPException(status_code=403, detail="Account disabled")
    user["session_ip"] = sess["ip"]
    return user


# --------------------------------------------------------- user lookup -------
def find_user_by_identifier(identifier: str) -> dict | None:
    ident = (identifier or "").strip().lower()
    if not ident:
        return None
    return dbm.query_one(
        "SELECT * FROM users WHERE lower(username)=? OR lower(email)=? "
        "ORDER BY CASE WHEN lower(email)=? THEN 0 ELSE 1 END LIMIT 1",
        (ident, ident, ident))


def authenticate(identifier: str, password: str) -> dict | None:
    """Email + password (username also accepted). Returns the user or None."""
    user = find_user_by_identifier(identifier)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user


# ------------------------------------------------------------- register ------
def register_user(username: str, password: str, capability: str, full_name: str,
                  department: str, security_question: str,
                  security_answer: str, email: str = "", phone: str = "",
                  *, created_by: str | None = None,
                  owner_admin: str | None = None,
                  must_change_password: bool = False,
                  email_verified: bool = False) -> dict:
    """Create a new USER account. Role is ALWAYS 'user'."""
    username = (username or "").strip().lower()
    if not username or not username.replace("_", "").replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400,
                            detail="Username: only letters, numbers, . _ - allowed")
    if username in (SUPERADMIN_USERNAME, DEFAULT_ADMIN_USERNAME):
        raise HTTPException(status_code=403, detail="This username is reserved")
    if len(password or "") < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    capability = (capability or "").strip().lower()
    caps = {"send": ["send"], "receiver": ["receive"], "receive": ["receive"],
            "sender": ["send"], "both": ["send", "receive"]}.get(capability)
    if not caps:
        raise HTTPException(status_code=400,
                            detail="Account type must be sender, receiver or both")
    if dbm.query_one("SELECT id FROM users WHERE username=?", (username,)):
        raise HTTPException(status_code=409, detail="Username already taken")
    email = (email or "").strip().lower()
    if email and dbm.query_one("SELECT id FROM users WHERE lower(email)=?", (email,)):
        raise HTTPException(status_code=409, detail="Email already registered")

    now = dbm.utcnow()
    dbm.execute(
        "INSERT INTO users(username, password_hash, role, capabilities, device_ip, "
        "created_at, updated_at, full_name, department, email, phone, created_by, "
        "owner_admin, must_change_password, email_verified, auth_provider, is_active) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (username, hash_password(password), "user", json.dumps(caps), None, now, now,
         (full_name or username).strip(), (department or "General").strip() or "General",
         email, (phone or "").strip(), created_by, owner_admin,
         1 if must_change_password else 0, 1 if email_verified else 0, "password"),
    )
    dbm.execute(
        "INSERT INTO recovery(username, question, answer_hash) VALUES(?,?,?) "
        "ON CONFLICT(username) DO UPDATE SET question=excluded.question, "
        "answer_hash=excluded.answer_hash",
        (username, security_question or DEFAULT_SECURITY_QUESTION,
         _hash_answer(security_answer)),
    )
    return {"username": username, "role": "user", "capabilities": caps,
            "full_name": full_name, "department": department}


# ------------------------------------------------------- account creation ----
def create_admin_account(email: str, full_name: str, password: str | None = None,
                         *, department: str = "Administration",
                         phone: str = "", aadhaar: str = "",
                         department_id: str = "", gender: str = "",
                         request_id: str | None = None,
                         created_by: str = SUPERADMIN_USERNAME) -> dict:
    """Create an online ADMIN account. Username/ID == email (lowercased).

    A strong temporary password is generated when none is supplied; the account
    is flagged ``must_change_password`` so the Admin changes it on first login.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    if email in (SUPERADMIN_USERNAME, DEFAULT_ADMIN_USERNAME):
        raise HTTPException(status_code=403, detail="This identifier is reserved")
    if dbm.query_one("SELECT id FROM users WHERE username=?", (email,)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    pwd = password or security.generate_password()
    now = dbm.utcnow()
    dbm.execute(
        "INSERT INTO users(username, password_hash, role, capabilities, device_ip, "
        "created_at, updated_at, full_name, department, email, phone, aadhaar, "
        "department_id, gender, created_by, must_change_password, email_verified, "
        "auth_provider, is_active) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (email, hash_password(pwd), "admin", None, None, now, now,
         (full_name or email).strip(), department or "Administration", email,
         phone, aadhaar, department_id, gender, created_by, 1, 1, "password"),
    )
    if request_id:
        dbm.execute(
            "UPDATE admin_requests SET status='APPROVED', decided_at=?, "
            "decided_by=?, generated_password=? WHERE request_id=?",
            (now, created_by, pwd, request_id),
        )
    return {"username": email, "role": "admin", "password": pwd,
            "full_name": full_name, "email": email, "department": department}


def create_sender(username: str, password: str, full_name: str, department: str,
                  email: str = "", phone: str = "", capability: str = "send",
                  *, owner_admin: str) -> dict:
    """Admin creates a Sender account under their management."""
    return register_user(
        username=username, password=password, capability=capability,
        full_name=full_name, department=department,
        security_question=DEFAULT_SECURITY_QUESTION, security_answer="",
        email=email, phone=phone, created_by=owner_admin, owner_admin=owner_admin)


# --------------------------------------------------------- admin requests ----
def create_admin_request(full_name: str, email: str, phone: str = "", aadhaar: str = "",
                         department_id: str = "", department: str = "",
                         gender: str = "") -> dict:
    email = (email or "").strip().lower()
    if not full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    if dbm.query_one("SELECT request_id FROM admin_requests WHERE email=? "
                     "AND status='PENDING'", (email,)):
        raise HTTPException(status_code=409,
                            detail="A pending request already exists for this email")
    year = datetime.now(timezone.utc).year
    count = dbm.query_one("SELECT COUNT(*) c FROM admin_requests")["c"] + 1
    request_id = f"ADMREQ-{year}-{count:04d}"
    dbm.execute(
        "INSERT INTO admin_requests(request_id, full_name, email, phone, aadhaar, "
        "department_id, department, gender, status, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,'PENDING',?)",
        (request_id, full_name.strip(), email, phone, aadhaar, department_id,
         department, gender, dbm.utcnow()),
    )
    return {"request_id": request_id, "status": "PENDING", "email": email,
            "full_name": full_name}


# ------------------------------------------------------- password resets -----
def create_password_reset_token(username: str,
                                ttl_seconds: int = PASSWORD_RESET_TTL_SECONDS) -> str:
    """Create a single-use reset token; store only its hash. Returns the raw token."""
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds, timezone.utc)
    # invalidate any previous unused tokens for this user
    dbm.execute("UPDATE password_reset_tokens SET used_at=? WHERE username=? "
                "AND used_at IS NULL", (now.isoformat(timespec="seconds"), username))
    dbm.execute(
        "INSERT INTO password_reset_tokens(token_hash, username, created_at, expires_at) "
        "VALUES(?,?,?,?)",
        (_hash_token(raw), username, now.isoformat(timespec="seconds"),
         expires.isoformat(timespec="seconds")),
    )
    return raw


def consume_password_reset_token(raw_token: str) -> str | None:
    """Validate + single-use-consume a reset token. Returns username or None."""
    if not raw_token:
        return None
    row = dbm.query_one("SELECT * FROM password_reset_tokens WHERE token_hash=?",
                        (_hash_token(raw_token),))
    if not row or row.get("used_at"):
        return None
    try:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return None
    except (TypeError, ValueError):
        return None
    dbm.execute("UPDATE password_reset_tokens SET used_at=? WHERE token_hash=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 row["token_hash"]))
    return row["username"]


def change_password(username: str, new_password: str,
                    *, clear_must_change: bool = True) -> None:
    if len(new_password or "") < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    dbm.execute(
        "UPDATE users SET password_hash=?, updated_at=?, must_change_password=? "
        "WHERE username=?",
        (hash_password(new_password), dbm.utcnow(),
         0 if clear_must_change else 1, username),
    )


# ---------------------------------------------------------- forgot (legacy) --
def get_recovery_question(username: str) -> str | None:
    row = dbm.query_one("SELECT question FROM recovery WHERE username=?",
                        ((username or "").strip().lower(),))
    return row["question"] if row else None


def reset_password_with_answer(username: str, answer: str, new_password: str) -> bool:
    username = (username or "").strip().lower()
    row = dbm.query_one("SELECT answer_hash FROM recovery WHERE username=?", (username,))
    if not row or row["answer_hash"] != _hash_answer(answer):
        return False
    user = dbm.query_one("SELECT role FROM users WHERE username=?", (username,))
    if not user or user["role"] in ("admin", "superadmin"):
        return False
    change_password(username, new_password)
    return True


# --------------------------------------------------------------- seeding -----
def ensure_superadmin() -> str:
    row = dbm.query_one("SELECT * FROM users WHERE username=?", (SUPERADMIN_USERNAME,))
    if row:
        if row["role"] != "superadmin":
            dbm.execute("UPDATE users SET role='superadmin', capabilities=NULL, "
                        "is_active=1 WHERE username=?", (SUPERADMIN_USERNAME,))
    else:
        now = dbm.utcnow()
        dbm.execute(
            "INSERT INTO users(username, password_hash, role, capabilities, device_ip, "
            "created_at, updated_at, full_name, department, email_verified, "
            "auth_provider, is_active) VALUES(?,?,?,?,?,?,?,?,?,1,'password',1)",
            (SUPERADMIN_USERNAME, hash_password(DEFAULT_SUPERADMIN_PASSWORD),
             "superadmin", None, None, now, now, "Super Administrator", "System"),
        )
    return SUPERADMIN_USERNAME


def ensure_default_admin() -> str | None:
    if not SEED_DEFAULT_ADMIN:
        return None
    row = dbm.query_one("SELECT * FROM users WHERE username=?", (DEFAULT_ADMIN_USERNAME,))
    if not row:
        now = dbm.utcnow()
        dbm.execute(
            "INSERT INTO users(username, password_hash, role, capabilities, device_ip, "
            "created_at, updated_at, full_name, department, email_verified, "
            "auth_provider, is_active) VALUES(?,?,?,?,?,?,?,?,?,1,'password',1)",
            (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD),
             "admin", None, None, now, now, "Administrator", "System"),
        )
    return DEFAULT_ADMIN_USERNAME


def create_default_users() -> dict:
    ensure_superadmin()
    ensure_default_admin()
    return {}
