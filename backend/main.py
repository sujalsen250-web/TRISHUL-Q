"""TRISHUL-Q -- FastAPI application.

One public domain/URL.  Everyone lands on the Main Landing Page and is directed
to Login / Request Admin Access / Sender / Receiver.  The Super Admin runs on a
separate, simpler panel that is enforced **localhost-only** on the server side.
The Admin (online) console is reachable from the public domain / LAN.

Three detection layers ("teen shool"):
  1. Bell-state teleportation integrity (replay + Pauli corrections)
  2. Pauli-eigenstate X/Y/Z basis verification (QBER)
  3. Statistical deviation (Hoeffding) + forgery-probability engine
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import time
import uuid
from datetime import datetime, timedelta as _timedelta, timezone
from pathlib import Path

from fastapi import (Depends, FastAPI, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, JSONResponse, RedirectResponse,
                               Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles

from . import audit
from . import config
from . import db as dbm
from . import events
from . import mailer
from . import metrics as srv_metrics
from . import ratelimit
from . import security
from . import startup as startup_checks
from .auth import (authenticate, change_password, consume_password_reset_token,
                   create_admin_account, create_admin_request,
                   create_default_users, create_password_reset_token,
                   create_sender, create_session, destroy_session,
                   destroy_user_sessions, ensure_superadmin,
                   find_user_by_identifier, get_capabilities, get_current_user,
                   get_session, hash_password, is_local_request,
                   require_capability, require_role, verify_password)
from .config import (ALLOWED_EXTENSIONS, APP_MODE, APP_NAME, APP_FULL_NAME,
                     FRONTEND_DIST, LOCAL_HOSTNAMES, MAX_FILE_SIZE,
                     ONLINE_WINDOW_SECONDS, SIGNATURE_TTL_SECONDS, SUPERADMIN_DIR,
                     UPLOAD_DIR, url_summary)

VERSION = config.VERSION

app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    description=f"{APP_FULL_NAME} — teleportation-based quantum digital "
                f"signature security (software simulation).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_START_TIME = time.time()


# ----------------------------------------------------------- middleware ------
@app.middleware("http")
async def superadmin_local_only_and_metrics(request: Request, call_next):
    """(a) SUPER ADMIN ISOLATION -- the super-admin panel and the whole
    /api/superadmin family are reachable ONLY from localhost. (b) request
    timing for the real server-information graph."""
    path = request.url.path
    if any(path == p or path.startswith(p + "/") or path.startswith(p)
           for p in config.SUPERADMIN_PATH_PREFIXES):
        host = (request.headers.get("host") or "").split(":")[0].lower()
        client = request.client.host if request.client else ""
        if host not in ({"testserver", "testclient"} | set(LOCAL_HOSTNAMES)) \
                or client not in ("127.0.0.1", "::1", "localhost", "testclient"):
            return JSONResponse(
                {"detail": "Super Admin panel is restricted to localhost "
                           "(http://127.0.0.1:%d/superadmin)" % (request.url.port or 8000)},
                status_code=403)

    t0 = time.perf_counter()
    response = await call_next(request)
    srv_metrics.note_request((time.perf_counter() - t0) * 1000)
    return response


@app.on_event("startup")
def on_startup() -> None:
    # --- 1. database: connect, create schema, migrate ---------------------
    try:
        dbm.init_db()
    except Exception as exc:                       # pragma: no cover
        print("\n" + "=" * 62)
        print("  FATAL: database is not available.")
        print(f"  {exc}")
        print("  Fix DATABASE_URL in .env and restart. (No silent SQLite fallback.)")
        print("=" * 62)
        raise

    # --- 2. seed the single permanent super-admin (and optional admin) ----
    create_default_users()

    # --- 3. real server-metrics collector ---------------------------------
    srv_metrics.start_collector()

    # --- 4. clear startup status banner -----------------------------------
    startup_checks.print_banner()
    err = startup_checks.fatal_db_error()
    if err:
        print(f"  [TRISHUL-Q] WARNING: {err}")

    # --- 5. warm up the quantum RNG in the background ---------------------
    try:
        from .quantum.qrng import warmup_async
        warmup_async()
    except Exception:
        print("  QRNG warmup skipped (will fall back at first use)")


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


# ------------------------------------------------------------- frontend ------
_HAS_DIST = (FRONTEND_DIST / "index.html").exists()
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")),
              name="assets")
if (SUPERADMIN_DIR / "static").is_dir():
    app.mount("/superadmin/static",
              StaticFiles(directory=str(SUPERADMIN_DIR / "static")),
              name="superadmin-static")


def _spa() -> Response:
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({
        "app": APP_NAME, "version": VERSION,
        "note": "React frontend not built yet. Run `npm install && npm run build` "
                "inside frontend/, or use the API at /docs.",
        "superadmin": "/superadmin",
    })


@app.get("/")
def index():
    return _spa()


@app.get("/superadmin")
def superadmin_page():
    page = SUPERADMIN_DIR / "index.html"
    if page.exists():
        return FileResponse(page)
    return JSONResponse({"detail": "superadmin panel not found"}, status_code=404)


# --------------------------------------------------------------------- auth --
def _redirect_for(user: dict) -> str:
    if user["role"] == "superadmin":
        return "/superadmin"
    if user["role"] == "admin":
        return "/admin"
    caps = get_capabilities(user)
    if "send" in caps and "receive" not in caps:
        return "/sender"
    if "receive" in caps:
        return "/receiver"
    return "/sender"


@app.post("/api/auth/login")
async def login(request: Request):
    """Email + password login (username is also accepted as an identifier)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    identifier = (body.get("email") or body.get("username") or "").strip()
    password = body.get("password") or ""
    ip = request.client.host if request.client else "unknown"

    allowed, retry = ratelimit.allow("login", ip, config.LOGIN_MAX_ATTEMPTS,
                                     config.LOGIN_WINDOW_SECONDS)
    if not allowed:
        audit.log(audit.FAILED_LOGIN, actor=identifier, result="rate-limited", ip=ip)
        raise HTTPException(status_code=429,
                            detail=f"Too many attempts. Please try again in {retry} seconds.")

    user = authenticate(identifier, password)
    if not user:
        audit.log(audit.FAILED_LOGIN, actor=identifier, result="failure", ip=ip)
        events.emit("LOGIN_FAILED", "MEDIUM",
                    f"Failed login attempt for '{identifier}'", source=ip)
        # generic message -- never reveal whether an email exists
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", 1):
        raise HTTPException(status_code=403,
                            detail="Account disabled. Please contact your administrator.")
    if user["role"] == "superadmin":
        raise HTTPException(status_code=403,
                            detail="Super Admin sign-in is only available on the "
                                   "local super-admin panel")

    ratelimit.reset("login", ip)
    token = create_session(user["username"], user["role"], ip)
    dbm.execute("UPDATE users SET device_ip=?, last_seen=?, last_login=? WHERE id=?",
                (ip, dbm.utcnow(), dbm.utcnow(), user["id"]))
    caps = get_capabilities(user)
    must_change = bool(user.get("must_change_password"))
    redirect = "/change-password" if must_change else _redirect_for(user)
    resp = JSONResponse({"ok": True, "role": user["role"], "capabilities": caps,
                         "redirect": redirect, "username": user["username"],
                         "must_change_password": must_change})
    resp.set_cookie("trishul_session", token, httponly=True, samesite="lax")
    audit.log(audit.EMAIL_LOGIN, actor=user["username"], result="success", ip=ip)
    events.emit("LOGIN", "INFO",
                f"{user['username']} authenticated as {user['role']}", source=ip)
    return resp


@app.post("/api/superadmin/login")
async def superadmin_login(request: Request):
    """Separate super-admin login -- localhost-only (see middleware)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    user = dbm.query_one("SELECT * FROM users WHERE username=?", (username,))
    if not user or user["role"] != "superadmin" or not verify_password(password, user["password_hash"]):
        events.emit("SUPERADMIN_LOGIN_FAILED", "HIGH",
                    f"Failed super-admin login attempt for '{username}'",
                    source=request.client.host if request.client else None)
        raise HTTPException(status_code=401, detail="Invalid super-admin credentials")
    ip = request.client.host if request.client else "unknown"
    token = create_session(username, "superadmin", ip)
    resp = JSONResponse({"ok": True, "role": "superadmin",
                         "redirect": "/superadmin", "username": username})
    resp.set_cookie("trishul_session", token, httponly=True, samesite="lax")
    audit.log(audit.SUPERADMIN_LOGIN, actor=username, result="success", ip=ip)
    events.emit("SUPERADMIN_LOGIN", "MEDIUM",
                f"Super Admin '{username}' authenticated (localhost)", source=ip)
    return resp


@app.post("/api/auth/logout")
async def logout(request: Request):
    token = request.cookies.get("trishul_session", "")
    sess = get_session(token)
    destroy_session(token)
    if sess:
        audit.log(audit.LOGOUT, actor=sess["username"],
                  ip=request.client.host if request.client else None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("trishul_session")
    return resp


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"],
            "capabilities": get_capabilities(user),
            "device_ip": user.get("device_ip"),
            "full_name": user.get("full_name") or user["username"].title(),
            "department": user.get("department") or "—",
            "email": user.get("email"),
            "must_change_password": bool(user.get("must_change_password")),
            "email_verified": bool(user.get("email_verified"))}


@app.post("/api/auth/register")
async def register(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    from .auth import register_user
    result = register_user(
        username=body.get("username") or "",
        password=body.get("password") or "",
        capability=(body.get("capability") or body.get("role") or "").lower(),
        full_name=body.get("full_name") or "",
        department=body.get("department") or "",
        security_question=body.get("security_question") or "",
        security_answer=body.get("security_answer") or "",
        email=body.get("email") or "",
        phone=body.get("phone") or "",
    )
    events.emit("USER_REGISTERED", "INFO",
                f"New user '{result['username']}' ({result['full_name']})")
    dbm.execute("INSERT INTO support_messages(from_user, to_user, body, created_at) "
                "VALUES('system','admin',?,?)",
                (f"New user: {result['full_name']}", dbm.utcnow()))
    return {"ok": True, **result}


@app.post("/api/auth/forgot/question")
async def forgot_question(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    from .auth import get_recovery_question
    question = get_recovery_question((body.get("username") or "").strip())
    if not question:
        raise HTTPException(status_code=404, detail="No recovery data for this username")
    return {"username": (body.get("username") or "").lower(), "question": question}


@app.post("/api/auth/forgot/reset")
async def forgot_reset(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    from .auth import reset_password_with_answer
    ok = reset_password_with_answer(body.get("username") or "",
                                    body.get("answer") or "",
                                    body.get("new_password") or "")
    if not ok:
        raise HTTPException(status_code=403, detail="Security answer is wrong")
    events.emit("PASSWORD_RESET", "MEDIUM",
                f"Password reset for '{(body.get('username') or '').strip().lower()}'")
    return {"ok": True, "message": "Password updated -- you can sign in now"}


# -------------------------------------------- forgot / reset / change pw ----
@app.post("/api/auth/forgot-password")
async def forgot_password(request: Request):
    """Request a password-reset link (single-use, hashed, expiring).

    Always returns the same success message so an attacker cannot tell whether
    an email is registered.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = (body.get("email") or "").strip().lower()
    ip = request.client.host if request.client else "unknown"
    allowed, retry = ratelimit.allow("reset", ip, config.RESET_MAX_REQUESTS,
                                     config.RESET_WINDOW_SECONDS)
    if not allowed:
        raise HTTPException(status_code=429,
                            detail=f"Too many requests. Please try again in {retry} seconds.")
    user = find_user_by_identifier(email)
    if user and user.get("is_active", 1) and user.get("role") != "superadmin":
        token = create_password_reset_token(user["username"])
        base = (config.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
        link = f"{base}/reset-password?token={token}"
        subject, msg = mailer.password_reset_email(
            user.get("full_name") or user["username"], link,
            config.PASSWORD_RESET_TTL_SECONDS // 60)
        recipient = (user.get("email") or email).strip()
        mail_result = mailer.send_mail(recipient, subject, msg)
        if not mail_result.get("sent"):
            # FIX: surface delivery failures instead of silently reporting success.
            events.emit("MAIL_FAILED", "MEDIUM",
                        f"Password-reset email to '{user['username']}' was not sent "
                        f"({mail_result.get('message')})", source=ip)
        audit.log(audit.PASSWORD_RESET_REQUESTED, actor=user["username"],
                  target=user["username"], ip=ip,
                  detail="email-sent" if mail_result.get("sent") else "email-skipped")
        events.emit("PASSWORD_RESET_REQUESTED", "MEDIUM",
                    f"Password reset requested for {user['username']}", source=ip)
    return {"ok": True,
            "message": "If that email is registered, a password reset link has been sent."}


@app.post("/api/auth/reset-password")
async def reset_password(request: Request):
    """Complete a reset with a valid single-use token."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    token = body.get("token") or ""
    new_password = body.get("new_password") or ""
    confirm = body.get("confirm_password")
    if confirm is not None and confirm != new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(new_password) < config.PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400,
                            detail=f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters")
    username = consume_password_reset_token(token)
    if not username:
        raise HTTPException(status_code=400,
                            detail="This reset link is invalid or has expired")
    change_password(username, new_password)
    destroy_user_sessions(username)
    row = dbm.query_one("SELECT full_name, email FROM users WHERE username=?", (username,))
    if row and row.get("email"):
        subj, msg = mailer.password_changed_email(row.get("full_name") or username)
        mailer.send_mail(row["email"], subj, msg)
    audit.log(audit.PASSWORD_RESET_COMPLETED, actor=username, target=username,
              ip=request.client.host if request.client else None)
    events.emit("PASSWORD_RESET", "MEDIUM", f"Password reset completed for {username}")
    return {"ok": True,
            "message": "Password reset successfully. Please login with your new password."}


@app.post("/api/auth/change-password")
async def change_password_endpoint(request: Request,
                                   user: dict = Depends(get_current_user)):
    """Change password. Also used for the forced first-login change."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    current = body.get("current_password") or ""
    new_password = body.get("new_password") or ""
    confirm = body.get("confirm_password")
    if confirm is not None and confirm != new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if not verify_password(current, user["password_hash"]):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if len(new_password) < config.PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400,
                            detail=f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters")
    if security.password_strength(new_password)["score"] < 2:
        raise HTTPException(status_code=400,
                            detail="Password too weak -- use upper/lower case, digits and symbols")
    change_password(user["username"], new_password)
    if user.get("email"):
        subj, msg = mailer.password_changed_email(user.get("full_name") or user["username"])
        mailer.send_mail(user["email"], subj, msg)
    audit.log(audit.PASSWORD_CHANGED, actor=user["username"],
              ip=request.client.host if request.client else None)
    return {"ok": True, "must_change_password": False, "message": "Password updated"}


# ---------------------------------------------------- admin registration -----
@app.post("/api/admin-requests")
async def submit_admin_request(request: Request):
    """Public: 'Request Admin Access' form."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    result = create_admin_request(
        full_name=body.get("full_name") or "",
        email=body.get("email") or "",
        phone=body.get("phone") or "",
        aadhaar=body.get("aadhaar") or "",
        department_id=body.get("department_id") or "",
        department=body.get("department") or "",
        gender=body.get("gender") or "",
    )
    events.emit("ADMIN_REQUEST", "INFO",
                f"Admin access request {result['request_id']} from "
                f"{result['full_name']} <{result['email']}>",
                target=result["request_id"])
    return {"ok": True, **result,
            "message": "Request submitted. The Super Admin will review it."}


@app.get("/api/admin-requests/status")
def admin_request_status(request_id: str = "", email: str = ""):
    """Public: check the status of an admin request by id or email."""
    if request_id:
        row = dbm.query_one("SELECT request_id, status, decided_at, note FROM "
                            "admin_requests WHERE request_id=?", (request_id.strip(),))
    elif email:
        row = dbm.query_one("SELECT request_id, status, decided_at, note FROM "
                            "admin_requests WHERE email=? ORDER BY id DESC LIMIT 1",
                            (email.strip().lower(),))
    else:
        raise HTTPException(status_code=400, detail="Provide request_id or email")
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


# ------------------------------------------------------------- directory -----
@app.get("/api/users/directory")
def user_directory(user: dict = Depends(get_current_user)):
    rows = dbm.query(
        "SELECT username, role, capabilities, full_name, department, last_seen, "
        "device_ip FROM users WHERE is_active=1 ORDER BY department, username")
    now = datetime.now(timezone.utc)
    rows = [r for r in rows
            if r.get("role") in ("admin", "superadmin")
            or "receive" in get_capabilities(r)]
    for r in rows:
        r["online"] = False
        if r.get("last_seen"):
            try:
                seen = datetime.fromisoformat(r["last_seen"])
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=timezone.utc)
                r["online"] = (now - seen).total_seconds() <= ONLINE_WINDOW_SECONDS
            except (TypeError, ValueError):
                pass
        r["full_name"] = r["full_name"] or r["username"].title()
        r["department"] = r["department"] or "General"
    return {"directory": rows}


@app.post("/api/heartbeat")
def heartbeat(request: Request, user: dict = Depends(get_current_user)):
    ip = request.client.host if request.client else None
    dbm.execute("UPDATE users SET last_seen=?, device_ip=? WHERE id=?",
                (dbm.utcnow(), ip or user.get("device_ip"), user["id"]))
    return {"ok": True}


# ------------------------------------------------------------------- system --
@app.get("/api/system/info")
def system_info(request: Request):
    from .quantum.qrng import backend_name as qrng_backend
    return {
        "app": APP_NAME, "full_name": APP_FULL_NAME, "version": VERSION,
        "lan_ip": get_lan_ip(), "port": request.url.port or 8000,
        "detected_url": str(request.base_url).rstrip("/"),
        "urls": url_summary(),
        "database": dbm.database_info(),
        "qrng_backend": qrng_backend(),
        "signature_ttl_seconds": SIGNATURE_TTL_SECONDS,
        "note": "Quantum-inspired software simulation -- no quantum hardware is used.",
    }


@app.get("/api/system/status")
def system_status(user: dict = Depends(get_current_user)):
    counts = {t: dbm.query_one(f"SELECT COUNT(*) c FROM {t}")["c"]
              for t in ("messages", "signatures", "security_events", "users",
                        "admin_requests")}
    return {"app": APP_NAME, "uptime_seconds": round(time.time() - _START_TIME, 1),
            "counts": counts, "settings": dbm.get_settings(),
            "database": dbm.database_info(),
            "role": user["role"], "username": user["username"]}


@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "time": dbm.utcnow(),
            "database": dbm.database_info()}


# ------------------------------------------------------------- google oauth --
_GOOGLE_CLIENT_ID = config.GOOGLE_CLIENT_ID
_GOOGLE_CLIENT_SECRET = config.GOOGLE_CLIENT_SECRET


def _google_redirect_uri(request: Request) -> str:
    """GOOGLE_REDIRECT_URI if configured, else derived from the request.

    Deriving from the request means the SAME build works on localhost AND on a
    public ngrok URL -- just add each callback URL to the Google console.
    """
    if config.GOOGLE_REDIRECT_URI:
        return config.GOOGLE_REDIRECT_URI
    return str(request.base_url).rstrip("/") + "/api/auth/google/callback"


@app.get("/api/auth/google/status")
def google_status():
    return {"configured": config.google_configured()}


@app.get("/api/auth/google/login")
def google_login(request: Request):
    if not config.google_configured():
        raise HTTPException(status_code=400, detail="Google login is not configured")
    from urllib.parse import urlencode
    params = urlencode({
        "client_id": _GOOGLE_CLIENT_ID,
        "redirect_uri": _google_redirect_uri(request),
        "response_type": "code", "scope": "openid email profile",
        "access_type": "online", "prompt": "select_account",
    })
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + params)


@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: str = "", error: str = ""):
    from urllib.parse import quote
    if error or not code:
        return RedirectResponse("/login?google_error=" + quote(error or "cancelled"))
    if not config.google_configured():
        return RedirectResponse("/login?google_error=not_configured")
    import httpx
    redirect_uri = _google_redirect_uri(request)
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            tok = await hc.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": _GOOGLE_CLIENT_ID,
                "client_secret": _GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"})
            tok.raise_for_status()
            info = await hc.get("https://openidconnect.googleapis.com/v1/userinfo",
                                headers={"Authorization": "Bearer "
                                         + tok.json().get("access_token", "")})
            info.raise_for_status()
            profile = info.json()
    except Exception:
        return RedirectResponse("/login?google_error=google_exchange_failed")

    email = (profile.get("email") or "").strip().lower()
    if not email:
        return RedirectResponse("/login?google_error=no_email")
    provider_id = str(profile.get("sub") or email)
    ip = request.client.host if request.client else "unknown"

    user = dbm.query_one("SELECT * FROM users WHERE lower(email)=?", (email,))
    if user:
        # SECURITY: Google login must NOT authenticate privileged accounts that
        # were created with a password. Those must use email + password.
        if user["role"] in ("admin", "superadmin") and user.get("auth_provider") != "google":
            audit.log(audit.GOOGLE_LOGIN, actor=email, result="blocked-privileged", ip=ip)
            return RedirectResponse("/login?google_error=use_password_for_this_account")
        if not user.get("is_active", 1):
            return RedirectResponse("/login?google_error=account_disabled")
    else:
        # FIX: no TRISHUL-Q account exists for this Google identity. We do NOT
        # silently create a default "receiver" account. The user must CREATE
        # an account first (choose Sender / Receiver / Both); we hand the
        # Google identity to the registration page to prefill.
        audit.log(audit.GOOGLE_LOGIN, actor=email, result="no-account", ip=ip)
        events.emit("GOOGLE_NO_ACCOUNT", "INFO",
                    f"Google sign-in with no TRISHUL-Q account: {email}", source=ip)
        return RedirectResponse(
            "/register?google=1&email=" + quote(email)
            + "&name=" + quote(profile.get("name") or ""))

    # link the OAuth identity (idempotent)
    try:
        if not dbm.query_one("SELECT id FROM oauth_accounts WHERE provider='google' "
                             "AND provider_user_id=?", (provider_id,)):
            dbm.execute("INSERT INTO oauth_accounts(provider, provider_user_id, "
                        "username, email, created_at) VALUES('google',?,?,?,?)",
                        (provider_id, user["username"], email, dbm.utcnow()))
    except Exception:
        pass

    token = create_session(user["username"], user["role"], ip)
    dbm.execute("UPDATE users SET device_ip=?, last_seen=?, last_login=? WHERE id=?",
                (ip, dbm.utcnow(), dbm.utcnow(), user["id"]))
    audit.log(audit.GOOGLE_LOGIN, actor=user["username"], result="success", ip=ip)
    resp = RedirectResponse(_redirect_for(user))
    resp.set_cookie("trishul_session", token, httponly=True, samesite="lax")
    return resp


# ---------------------------------------------------------- quantum layer ----
@app.get("/api/qrng/health")
def qrng_health(user: dict = Depends(get_current_user)):
    from .quantum.qrng import health_check
    return health_check()


@app.get("/api/qec/curve")
def qec_curve(user: dict = Depends(get_current_user)):
    from .quantum.qec import protection_curve
    return {"code": "3-qubit bit-flip repetition (majority vote)",
            "logical_error_formula": "P_L = 3p^2 - 2p^3",
            "points": protection_curve(21)}


@app.get("/api/quantum/pauli")
def quantum_pauli(user: dict = Depends(get_current_user)):
    """Reference table of the six Pauli eigenstates used by the QDS key."""
    from .quantum.pauli_eigenstates import (BASES, BASIS_LABEL, EIGENSTATES, label)
    out = []
    for b in BASES:
        states = []
        for bit in (0, 1):
            vec = EIGENSTATES[(b, bit)]
            states.append({"bit": bit, "label": label(b, bit),
                           "amplitude": [round(float(vec[0].real), 4),
                                         round(float(vec[0].imag), 4),
                                         round(float(vec[1].real), 4),
                                         round(float(vec[1].imag), 4)]})
        out.append({"basis": b, "label": BASIS_LABEL[b], "states": states})
    return {"bases": out,
            "note": "Bob measures each qubit in a random X/Y/Z basis; a matching "
                    "basis gives the deterministic eigenvalue, a mismatch is discarded."}


@app.post("/api/thresholds/calibrate")
async def calibrate_thresholds_endpoint(request: Request,
                                        user: dict = Depends(require_role("admin"))):
    from .detection.calibration import calibrate_thresholds
    try:
        body = await request.json()
    except Exception:
        body = {}
    report = calibrate_thresholds(int(dbm.get_setting("n_measurements")))
    if body.get("apply"):
        dbm.set_setting("threshold_suspicious", str(report["threshold_suspicious"]))
        dbm.set_setting("threshold_threat", str(report["threshold_threat"]))
        events.emit("SETTINGS_UPDATED", "INFO",
                    f"3-sigma calibration applied by {user['username']}")
    return report


# ---------------------------------------------------------------- signature --
@app.post("/api/signature/generate")
async def generate_signature(request: Request,
                             user: dict = Depends(require_capability("send"))):
    from .qds.signature import generate_signature as gen, sha256_hex
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = body.get("message", "")
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message text is required")
    bell_state = body.get("bell_state", dbm.get_setting("default_bell_state"))
    n_qubits = int(body.get("n_qubits") or dbm.get_setting("n_qubits"))
    n_qubits = max(4, min(128, n_qubits))
    message_hash = sha256_hex(message)
    sig = gen(message_hash, user["username"],
              request.client.host if request.client else None,
              bell_state=bell_state, n_qubits=n_qubits)
    sig["expires_at"] = (datetime.now(timezone.utc)
                         + _timedelta(seconds=SIGNATURE_TTL_SECONDS)
                         ).isoformat(timespec="seconds")
    return sig


def _validate_and_store_file(upload: UploadFile | None):
    if upload is None or not upload.filename:
        return None, None, 0
    name = upload.filename
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80] or "file"
    stored_name = f"{uuid.uuid4().hex[:10]}_{safe}"
    path = UPLOAD_DIR / stored_name
    import hashlib
    hasher = hashlib.sha256()
    size = 0
    with open(path, "wb") as fh:
        while chunk := upload.file.read(64 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                fh.close(); os.remove(path)
                raise HTTPException(status_code=400,
                                    detail=f"File exceeds {MAX_FILE_SIZE // (1024*1024)} MB")
            fh.write(chunk); hasher.update(chunk)
    return str(path), hasher.hexdigest(), size


@app.post("/api/send")
async def send_message(request: Request,
                       message: str = Form(...),
                       signature_id: str = Form(...),
                       nonce: str = Form(...),
                       receiver_username: str = Form(""),
                       file: UploadFile | None = File(None),
                       user: dict = Depends(require_capability("send"))):
    from .qds.signature import sha256_hex
    from .qds.verification import verify_message

    t_start = time.perf_counter()
    receiver_username = (receiver_username or "").strip().lower()
    if not receiver_username:
        raise HTTPException(status_code=400, detail="Choose a recipient")
    recipient = dbm.query_one("SELECT * FROM users WHERE username=?", (receiver_username,))
    if not recipient or not recipient.get("is_active", 1):
        raise HTTPException(status_code=404, detail="Recipient not found")
    if "receive" not in get_capabilities(recipient):
        raise HTTPException(status_code=400,
                            detail="Recipient cannot receive (no receive capability)")

    sig = dbm.query_one("SELECT * FROM signatures WHERE signature_id=?", (signature_id,))
    if not sig:
        raise HTTPException(status_code=404, detail="Signature not found")
    if sig["sender_username"] != user["username"]:
        raise HTTPException(status_code=403, detail="Signature does not belong to this sender")
    if sig["nonce"] != nonce:
        raise HTTPException(status_code=400, detail="Nonce does not match signature")

    try:
        sig_created = datetime.fromisoformat(sig["created_at"])
        if sig_created.tzinfo is None:
            sig_created = sig_created.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - sig_created).total_seconds()
    except (TypeError, ValueError):
        age = 0.0
    if age > SIGNATURE_TTL_SECONDS:
        events.emit("SIGNATURE_EXPIRED", "MEDIUM",
                    f"Signature {signature_id} expired after {int(age)} s",
                    target=signature_id)
        raise HTTPException(status_code=400,
                            detail=f"QDS signature EXPIRED (valid only "
                                   f"{SIGNATURE_TTL_SECONDS} s) -- regenerate and resend")

    message_hash = sha256_hex(message)
    if message_hash != sig["message_hash"]:
        raise HTTPException(status_code=400,
                            detail="Message was modified after signature generation")

    if dbm.query_one("SELECT nonce FROM used_nonces WHERE nonce=?", (nonce,)):
        raise HTTPException(status_code=409, detail="Replay attempt blocked: nonce already used")

    file_path, file_hash, file_size = _validate_and_store_file(file)

    year = datetime.now(timezone.utc).year
    count = dbm.query_one("SELECT COUNT(*) c FROM messages")["c"] + 1
    message_id = f"MSG-{year}-{count:04d}"
    now = dbm.utcnow()
    sender_ip = request.client.host if request.client else None
    receiver_ip = get_lan_ip()
    dbm.execute(
        "INSERT INTO messages(message_id, sender_id, receiver_id, sender_ip, receiver_ip, "
        "message, file_name, file_path, file_hash, message_hash, signature_id, nonce, "
        "timestamp, status, created_at, delivery_status) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING')",
        (message_id, user["username"], receiver_username, sender_ip, receiver_ip,
         message, Path(file_path).name if file_path else None, file_path, file_hash,
         message_hash, signature_id, nonce, now, "PENDING", now))
    dbm.execute("INSERT INTO used_nonces(nonce, signature_id, used_at) VALUES(?,?,?)",
                (nonce, signature_id, now))
    dbm.execute("UPDATE signatures SET message_id=? WHERE signature_id=?",
                (message_id, signature_id))
    events.emit("MESSAGE_RECEIVED", "INFO",
                f"Message {message_id} from {user['username']} to {receiver_username}",
                source=sender_ip, target=message_id)

    file_bytes = Path(file_path).read_bytes() if file_path else None
    thresholds = (float(dbm.get_setting("threshold_suspicious")),
                  float(dbm.get_setting("threshold_threat")))
    n_measurements = int(dbm.get_setting("n_measurements"))
    verdict = verify_message(message, file_bytes, file_hash, sig, n_measurements,
                             thresholds, claimed_sender=user["username"],
                             actual_source_ip=sender_ip)

    status = {"ACCEPT": "VERIFIED", "FLAG": "SUSPICIOUS", "REJECT": "REJECTED"}[verdict["action"]]
    msg_row = dbm.query_one("SELECT id FROM messages WHERE message_id=?", (message_id,))
    dbm.execute("UPDATE messages SET status=?, verdict=?, deviation=?, verified_at=? WHERE id=?",
                (status, json.dumps(verdict), verdict["deviation"], dbm.utcnow(),
                 msg_row["id"]))
    if verdict["action"] == "REJECT":
        dbm.execute("UPDATE messages SET delivery_status='FAILED', ack_at=?, "
                    "ack_note='receiver verification rejected the message' WHERE id=?",
                    (dbm.utcnow(), msg_row["id"]))
        events.emit("DELIVERY_FAILED", "HIGH",
                    f"Delivery of {message_id} FAILED ({verdict['classification']})",
                    source=sender_ip, target=message_id)
    dbm.execute("UPDATE signatures SET verification_status=?, n_measurements=? WHERE id=?",
                (status, n_measurements, sig["id"]))

    pv = verdict.get("pauli_verification") or {}
    dbm.execute("INSERT INTO verification_events(message_id, signature_id, classification, "
                "action, deviation, pauli_checks, pauli_mismatch_rate, source, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (message_id, signature_id, verdict["classification"], verdict["action"],
                 verdict["deviation"], pv.get("checked"), pv.get("mismatch_rate"),
                 sender_ip, dbm.utcnow()))

    total_ms = (time.perf_counter() - t_start) * 1000
    dbm.execute("INSERT INTO performance_metrics(operation, duration_ms, ref_id, created_at) "
                "VALUES('verification',?,?,?)",
                (verdict["verification_time_ms"], message_id, dbm.utcnow()))
    dbm.execute("INSERT INTO performance_metrics(operation, duration_ms, ref_id, created_at) "
                "VALUES('total_processing',?,?,?)", (total_ms, message_id, dbm.utcnow()))

    if verdict["action"] == "ACCEPT":
        events.emit("SIGNATURE_VERIFIED", "INFO",
                    f"Signature {signature_id} valid -- deviation {verdict['deviation']}",
                    source=sender_ip, target=message_id, extra={"verdict": verdict})
    else:
        events.emit("VERIFICATION_FAILED", "HIGH",
                    f"Message {message_id} {status} -- {verdict['classification']}: "
                    + "; ".join(verdict["reasons"] or ["statistical deviation"]),
                    source=sender_ip, target=message_id, extra={"verdict": verdict})

    return {"message_id": message_id, "signature_id": signature_id,
            "file_name": Path(file_path).name if file_path else None,
            "file_size": file_size, "file_hash": file_hash, "verdict": verdict,
            "total_time_ms": round(total_ms, 2)}


# ---------------------------------------------------------- messages / view --
def _can_access_message(user: dict, row: dict) -> bool:
    return (user["role"] in ("admin", "superadmin")
            or row["sender_id"] == user["username"]
            or row["receiver_id"] == user["username"])


def _emit_unauthorized_verification(user: dict, message_id: str,
                                    request: Request | None, action: str) -> None:
    """Unauthorized verification is a FIRST-CLASS security event.

    Raised when a user tries to verify / read / download / acknowledge a
    message that is not addressed to them (wrong session, wrong identity, or a
    stolen signature id).  Recorded in the threat log and pushed over SSE.
    """
    events.emit(
        "UNAUTHORIZED_VERIFICATION", "HIGH",
        f"Unauthorized verification: user '{user['username']}' attempted to "
        f"{action} message {message_id} which is not addressed to them "
        f"(receiver/sender mismatch or stolen signature id)",
        source=(request.client.host if request and request.client else None),
        target=message_id,
    )


@app.get("/api/messages/sent")
def my_sent_messages(user: dict = Depends(require_capability("send"))):
    rows = dbm.query(
        "SELECT m.message_id, m.receiver_id, u.full_name AS receiver_name, "
        "u.department AS receiver_dept, m.message, m.file_name, m.message_hash, "
        "m.file_hash, m.signature_id, m.nonce, m.timestamp, m.status, m.deviation, "
        "m.delivery_status, m.ack_at, m.ack_note FROM messages m "
        "LEFT JOIN users u ON u.username = m.receiver_id "
        "WHERE m.sender_id=? ORDER BY m.id DESC", (user["username"],))
    return {"messages": rows}


@app.get("/api/messages/received")
def received_messages(user: dict = Depends(require_capability("receive"))):
    if user["role"] in ("admin", "superadmin"):
        rows = dbm.query(
            "SELECT m.message_id, m.sender_id, u.full_name AS sender_name, "
            "u.department AS sender_dept, m.sender_ip, m.message, m.file_name, "
            "m.message_hash, m.file_hash, m.signature_id, m.nonce, m.timestamp, "
            "m.status, m.deviation, m.delivery_status, m.ack_at, m.ack_note, "
            "m.created_at FROM messages m LEFT JOIN users u ON u.username = m.sender_id "
            "ORDER BY m.id DESC")
    else:
        rows = dbm.query(
            "SELECT m.message_id, m.sender_id, u.full_name AS sender_name, "
            "u.department AS sender_dept, m.sender_ip, m.message, m.file_name, "
            "m.message_hash, m.file_hash, m.signature_id, m.nonce, m.timestamp, "
            "m.status, m.deviation, m.delivery_status, m.ack_at, m.ack_note, "
            "m.created_at FROM messages m LEFT JOIN users u ON u.username = m.sender_id "
            "WHERE m.receiver_id=? ORDER BY m.id DESC", (user["username"],))
    return {"messages": rows}


@app.get("/api/messages")
def list_messages(user: dict = Depends(require_role("admin"))):
    rows = dbm.query(
        "SELECT message_id, sender_id, receiver_id, sender_ip, receiver_ip, message, "
        "file_name, file_hash, message_hash, signature_id, nonce, timestamp, status, "
        "deviation, created_at FROM messages ORDER BY id DESC")
    return {"messages": rows}


@app.get("/api/messages/{message_id}")
def get_message(message_id: str, request: Request,
                user: dict = Depends(get_current_user)):
    row = dbm.query_one("SELECT * FROM messages WHERE message_id=?", (message_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if not _can_access_message(user, row):
        _emit_unauthorized_verification(user, message_id, request, "read")
        raise HTTPException(status_code=403, detail="This message is not addressed to you")
    sig = dbm.query_one(
        "SELECT signature_id, bell_state, quantum_state, n_qubits, n_measurements, "
        "expected_distribution, teleports, verification_status, created_at "
        "FROM signatures WHERE signature_id=?", (row["signature_id"],))
    try:
        verdict = json.loads(row["verdict"]) if row["verdict"] else None
    except (TypeError, ValueError):
        verdict = None
    return {"message": row, "signature": sig, "verdict": verdict}


@app.get("/api/messages/{message_id}/file")
def download_file(message_id: str, request: Request,
                  user: dict = Depends(get_current_user)):
    row = dbm.query_one("SELECT file_path, file_name, delivery_status, id, sender_id, "
                        "receiver_id FROM messages WHERE message_id=?", (message_id,))
    if not row or not row["file_path"]:
        raise HTTPException(status_code=404, detail="No attachment for this message")
    if not _can_access_message(user, row):
        _emit_unauthorized_verification(user, message_id, request, "download")
        raise HTTPException(status_code=403, detail="This message is not addressed to you")
    real = os.path.realpath(row["file_path"])
    if not real.startswith(os.path.realpath(str(UPLOAD_DIR))):
        raise HTTPException(status_code=403, detail="Path traversal blocked")
    if not os.path.exists(real):
        raise HTTPException(status_code=404, detail="Stored file is missing")
    if row["delivery_status"] in ("PENDING", None):
        dbm.execute("UPDATE messages SET delivery_status='DELIVERED', ack_at=? WHERE id=?",
                    (dbm.utcnow(), row["id"]))
        events.emit("DELIVERY_ACK", "INFO",
                    f"Receiver downloaded attachment of {message_id}", target=message_id)
    return FileResponse(real, filename=row["file_name"] or "attachment")


@app.post("/api/messages/{message_id}/ack")
async def ack_message(message_id: str, request: Request,
                      user: dict = Depends(require_capability("receive"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    ack = (body.get("status") or "").upper()
    if ack not in ("DELIVERED", "READ", "FAILED"):
        raise HTTPException(status_code=400, detail="status must be DELIVERED, READ or FAILED")
    note = (body.get("note") or "").strip()[:200]
    row = dbm.query_one("SELECT id, sender_id, receiver_id, delivery_status FROM messages "
                        "WHERE message_id=?", (message_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if not _can_access_message(user, row):
        _emit_unauthorized_verification(user, message_id, request, "acknowledge")
        raise HTTPException(status_code=403, detail="This message is not addressed to you")
    if row["delivery_status"] == "READ" and ack == "DELIVERED":
        ack = "READ"
    dbm.execute("UPDATE messages SET delivery_status=?, ack_at=?, ack_note=? WHERE id=?",
                (ack, dbm.utcnow(), note or None, row["id"]))
    events.emit("DELIVERY_ACK", "INFO",
                f"Receiver acknowledged {message_id}: {ack}", target=message_id)
    return {"message_id": message_id, "delivery_status": ack, "ack_at": dbm.utcnow()}


@app.post("/api/verify/{message_id}")
def reverify(message_id: str, request: Request,
             user: dict = Depends(get_current_user)):
    from .qds.verification import verify_message
    row = dbm.query_one("SELECT * FROM messages WHERE message_id=?", (message_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if not _can_access_message(user, row):
        _emit_unauthorized_verification(user, message_id, request, "re-verify")
        raise HTTPException(status_code=403, detail="This message is not addressed to you")
    sig = dbm.query_one("SELECT * FROM signatures WHERE signature_id=?",
                        (row["signature_id"],))
    file_bytes = Path(row["file_path"]).read_bytes() if row["file_path"] else None
    thresholds = (float(dbm.get_setting("threshold_suspicious")),
                  float(dbm.get_setting("threshold_threat")))
    verdict = verify_message(row["message"] or "", file_bytes, row["file_hash"], sig,
                             int(dbm.get_setting("n_measurements")), thresholds,
                             claimed_sender=row["sender_id"],
                             actual_source_ip=row["sender_ip"])
    status = {"ACCEPT": "VERIFIED", "FLAG": "SUSPICIOUS", "REJECT": "REJECTED"}[verdict["action"]]
    dbm.execute("UPDATE messages SET status=?, verdict=?, deviation=? WHERE id=?",
                (status, json.dumps(verdict), verdict["deviation"], row["id"]))
    events.emit("RE_VERIFICATION", "INFO",
                f"Manual re-verification of {message_id}: {verdict['classification']}",
                target=message_id, extra={"verdict": verdict})
    return {"message_id": message_id, "verdict": verdict}


# ------------------------------------------------------------- security ------
@app.get("/api/security/events")
def security_events(limit: int = 100, event_type: str = "",
                    user: dict = Depends(require_role("admin"))):
    limit = max(1, min(500, limit))
    if event_type:
        rows = dbm.query("SELECT * FROM security_events WHERE event_type=? "
                         "ORDER BY id DESC LIMIT ?", (event_type, limit))
    else:
        rows = dbm.query("SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,))
    return {"events": rows}


@app.get("/api/statistics")
def statistics(user: dict = Depends(require_role("admin"))):
    def count(sql, params=()):
        return dbm.query_one(sql, params)["c"]

    perf = {r["operation"]: {"avg_ms": round(r["avg"], 2), "n": r["n"]}
            for r in dbm.query("SELECT operation, AVG(duration_ms) avg, COUNT(*) n "
                               "FROM performance_metrics GROUP BY operation")}
    series = {
        "verification_times": [r["duration_ms"] for r in dbm.query(
            "SELECT duration_ms FROM performance_metrics WHERE operation='verification' "
            "ORDER BY id DESC LIMIT 20")][::-1],
        "signature_times": [r["duration_ms"] for r in dbm.query(
            "SELECT duration_ms FROM performance_metrics WHERE "
            "operation='signature_generation' ORDER BY id DESC LIMIT 20")][::-1],
    }

    def dcount(cond, params=()):
        return count(f"SELECT COUNT(*) c FROM messages WHERE {cond}", params)
    delivery = {
        "verified": dcount("status='VERIFIED'"),
        "suspicious": dcount("status='SUSPICIOUS'"),
        "rejected": dcount("status='REJECTED'"),
        "delivered": dcount("delivery_status IN ('DELIVERED','READ')"),
        "read": dcount("delivery_status='READ'"),
        "pending": dcount("delivery_status='PENDING'"),
        "failed": dcount("delivery_status='FAILED'"),
    }
    delivery["success"] = dcount("status='VERIFIED' AND delivery_status IN ('DELIVERED','READ')")
    delivery["failed_total"] = delivery["failed"] + delivery["rejected"]

    return {
        "counts": {
            "messages_received": count("SELECT COUNT(*) c FROM messages"),
            "verified_signatures": count("SELECT COUNT(*) c FROM messages WHERE status='VERIFIED'"),
            "threats_detected": count("SELECT COUNT(*) c FROM messages "
                                      "WHERE status IN ('SUSPICIOUS','REJECTED')"),
            "users_total": count("SELECT COUNT(*) c FROM users"),
            "admins_total": count("SELECT COUNT(*) c FROM users WHERE role='admin'"),
            "admin_requests_pending": count("SELECT COUNT(*) c FROM admin_requests "
                                            "WHERE status='PENDING'"),
            "unauthorized_verifications": count("SELECT COUNT(*) c FROM security_events "
                                                "WHERE event_type='UNAUTHORIZED_VERIFICATION'"),
        },
        "delivery": delivery,
        "performance": perf,
        "series": series,
        "generated_at": dbm.utcnow(),
    }


@app.get("/api/security/analysis")
def security_analysis(n_qubits: int = 0, trials: int = 150,
                      user: dict = Depends(require_role("admin"))):
    """Live Security-Analysis panel data (admin only).

    Computed LIVE from the forgery-probability engine + the live DB. A snapshot
    of the run is persisted so the P_forge curve is historical.
    """
    from .detection import forgery
    n_qubits = max(4, min(128, int(n_qubits or dbm.get_setting("n_qubits"))))
    trials = max(20, min(800, int(trials)))
    result = forgery.analysis(n_qubits=n_qubits, trials=trials)
    dbm.execute("INSERT INTO analysis_snapshots(n_qubits, checks, p_forge, p_honest, "
                "payload, created_at) VALUES(?,?,?,?,?,?)",
                (result["n_qubits"], result["checks"], result["p_forge_closed_form"],
                 result["honest"]["p_honest"], json.dumps(result), dbm.utcnow()))
    # live DB facts alongside the simulation
    result["live"] = {
        "messages_total": dbm.query_one("SELECT COUNT(*) c FROM messages")["c"],
        "rejected": dbm.query_one("SELECT COUNT(*) c FROM messages "
                                  "WHERE status='REJECTED'")["c"],
        "unauthorized_verifications": dbm.query_one(
            "SELECT COUNT(*) c FROM security_events "
            "WHERE event_type='UNAUTHORIZED_VERIFICATION'")["c"],
    }
    return result


@app.get("/api/security/analysis/history")
def security_analysis_history(limit: int = 30,
                              user: dict = Depends(require_role("admin"))):
    rows = dbm.query("SELECT n_qubits, checks, p_forge, p_honest, created_at "
                     "FROM analysis_snapshots ORDER BY id DESC LIMIT ?",
                     (max(1, min(200, limit)),))
    return {"snapshots": rows[::-1]}


@app.get("/api/attack-analytics")
def attack_analytics(user: dict = Depends(require_role("admin"))):
    """Attack analytics from LIVE security_events rows (no hardcoded values)."""
    rows = dbm.query("SELECT event_type, COUNT(*) c FROM security_events "
                     "GROUP BY event_type ORDER BY c DESC")
    sev = dbm.query("SELECT severity, COUNT(*) c FROM security_events "
                    "GROUP BY severity")
    return {"by_type": rows, "by_severity": sev,
            "unauthorized": dbm.query_one(
                "SELECT COUNT(*) c FROM security_events "
                "WHERE event_type='UNAUTHORIZED_VERIFICATION'")["c"]}


# ---------------------------------------------------------------- devices ----
@app.get("/api/devices")
def devices(user: dict = Depends(require_role("admin"))):
    users = dbm.query("SELECT username, role, device_ip, created_at, last_seen, "
                      "full_name, department FROM users ORDER BY role")
    now = datetime.now(timezone.utc)
    for u in users:
        u["online"] = False
        if u.get("last_seen"):
            try:
                seen = datetime.fromisoformat(u["last_seen"])
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=timezone.utc)
                u["online"] = (now - seen).total_seconds() <= ONLINE_WINDOW_SECONDS
            except (TypeError, ValueError):
                pass
    return {"devices": users, "online_count": sum(1 for u in users if u["online"])}


@app.get("/api/admin/online")
def admin_online(user: dict = Depends(require_role("admin"))):
    return devices(user)


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(require_role("admin"))):
    rows = dbm.query("SELECT username, role, capabilities, full_name, department, email, "
                     "phone, device_ip, created_at, last_seen, is_active FROM users "
                     "ORDER BY role, username")
    return {"users": rows}


@app.post("/api/admin/change-password")
async def admin_change_password(request: Request,
                                user: dict = Depends(require_role("admin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    new = body.get("new_password") or ""
    if len(new) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    if not verify_password(body.get("current_password") or "", user["password_hash"]):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    dbm.execute("UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(new), user["id"]))
    events.emit("PASSWORD_CHANGED", "MEDIUM", f"Admin {user['username']} changed password")
    return {"ok": True}


# ------------------------------------------------- admin <-> superadmin msg --
@app.post("/api/admin/message-superadmin")
async def admin_message_superadmin(request: Request,
                                   user: dict = Depends(require_role("admin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = (body.get("body") or "").strip()[:1000]
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    dbm.execute("INSERT INTO admin_messages(from_user, to_user, body, created_at) "
                "VALUES(?,?,?,?)", (user["username"], config.SUPERADMIN_USERNAME,
                                    text, dbm.utcnow()))
    events.emit("ADMIN_MESSAGE", "INFO",
                f"Admin {user['username']} messaged the Super Admin")
    return {"ok": True}


@app.get("/api/admin/messages")
def admin_messages(user: dict = Depends(require_role("admin"))):
    rows = dbm.query("SELECT * FROM admin_messages WHERE from_user=? OR to_user=? "
                     "ORDER BY id ASC LIMIT 300", (user["username"], user["username"]))
    dbm.execute("UPDATE admin_messages SET read_at=? WHERE to_user=? AND read_at IS NULL",
                (dbm.utcnow(), user["username"]))
    return {"messages": rows}


# ---------------------------------------------------------------- support ----
@app.post("/api/support")
async def support_send(request: Request, user: dict = Depends(get_current_user)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = (body.get("body") or "").strip()[:1000]
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    dbm.execute("INSERT INTO support_messages(from_user, to_user, body, created_at) "
                "VALUES(?,?,?,?)", (user["username"], "admin", text, dbm.utcnow()))
    events.emit("SUPPORT_MESSAGE", "INFO",
                f"Support request from {user['username']}: {text[:80]}")
    return {"ok": True, "created_at": dbm.utcnow()}


@app.get("/api/support/mine")
def support_mine(user: dict = Depends(get_current_user)):
    if user["role"] == "admin":
        rows = dbm.query("SELECT * FROM support_messages WHERE to_user='admin' "
                         "ORDER BY id DESC LIMIT 200")[::-1]
    else:
        rows = dbm.query("SELECT * FROM support_messages WHERE from_user=? OR to_user=? "
                         "ORDER BY id DESC LIMIT 200",
                         (user["username"], user["username"]))[::-1]
    return {"messages": rows}


@app.get("/api/support/threads")
def support_threads(user: dict = Depends(require_role("admin"))):
    rows = dbm.query(
        "SELECT u.username, u.full_name, u.department, u.role, "
        "(SELECT COUNT(*) FROM support_messages s WHERE s.from_user = u.username "
        " AND s.to_user='admin' AND s.read_at IS NULL) AS unread, "
        "(SELECT MAX(s.created_at) FROM support_messages s "
        " WHERE s.from_user = u.username OR s.to_user = u.username) AS last_at "
        "FROM users u WHERE u.role = 'user' "
        "AND EXISTS (SELECT 1 FROM support_messages s WHERE s.from_user = u.username) "
        "ORDER BY last_at DESC")
    for r in rows:
        r["full_name"] = r["full_name"] or r["username"].title()
    return {"threads": rows}


@app.get("/api/support/thread/{username}")
def support_thread(username: str, user: dict = Depends(require_role("admin"))):
    username = (username or "").strip().lower()
    rows = dbm.query("SELECT * FROM support_messages WHERE from_user=? OR to_user=? "
                     "ORDER BY id ASC LIMIT 300", (username, username))
    dbm.execute("UPDATE support_messages SET read_at=? WHERE from_user=? AND "
                "to_user='admin' AND read_at IS NULL", (dbm.utcnow(), username))
    return {"messages": rows, "username": username}


@app.post("/api/support/reply")
async def support_reply(request: Request, user: dict = Depends(require_role("admin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    to_user = (body.get("to_user") or "").strip().lower()
    text = (body.get("body") or "").strip()[:1000]
    if not text or not to_user:
        raise HTTPException(status_code=400, detail="to_user and body are required")
    if not dbm.query_one("SELECT id FROM users WHERE username=?", (to_user,)):
        raise HTTPException(status_code=404, detail="User not found")
    dbm.execute("INSERT INTO support_messages(from_user, to_user, body, created_at) "
                "VALUES(?,?,?,?)", ("admin", to_user, text, dbm.utcnow()))
    return {"ok": True, "created_at": dbm.utcnow()}


# --------------------------------------------------------------- settings ----
@app.get("/api/settings")
def get_settings_route(user: dict = Depends(require_role("admin"))):
    return {"settings": dbm.get_settings()}


@app.put("/api/settings")
async def update_settings(request: Request, user: dict = Depends(require_role("admin"))):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    allowed = {"threshold_suspicious", "threshold_threat", "n_measurements",
               "n_qubits", "replay_window_seconds", "default_bell_state",
               "pauli_mismatch_threshold"}
    for key, value in body.items():
        if key not in allowed:
            continue
        if key in ("threshold_suspicious", "threshold_threat", "pauli_mismatch_threshold"):
            v = float(value)
            if not 0.0 < v < 1.0:
                raise HTTPException(status_code=400, detail=f"Invalid threshold: {key}")
        elif key in ("n_measurements", "n_qubits", "replay_window_seconds"):
            v = int(value)
            if v <= 0:
                raise HTTPException(status_code=400, detail=f"Invalid value: {key}")
        else:
            v = str(value)
        dbm.set_setting(key, str(v))
    events.emit("SETTINGS_UPDATED", "INFO", f"Settings updated by {user['username']}")
    return {"settings": dbm.get_settings()}


# ------------------------------------------------------------ SSE / metrics --
@app.get("/api/events/stream")
async def event_stream(user: dict = Depends(get_current_user)):
    queue = events.BUS.subscribe()

    async def generator():
        try:
            yield f"data: {json.dumps({'event_type': 'STREAM_CONNECTED', 'severity': 'INFO', 'description': 'Live security stream connected'})}\n\n"
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {events.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events.BUS.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/api/admin/metrics")
def admin_metrics(limit: int = 60, user: dict = Depends(require_role("admin"))):
    return {"current": srv_metrics.snapshot(), "series": srv_metrics.series(limit),
            "psutil": srv_metrics.psutil_available()}


@app.get("/api/system/qr")
def system_qr(request: Request):
    try:
        import io
        import qrcode
        img = qrcode.make(f"http://{get_lan_ip()}:{request.url.port or 8000}")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    except ImportError:
        raise HTTPException(status_code=503, detail="qrcode package not installed")


# =====================================================================
#  SUPER ADMIN  (localhost only -- enforced in middleware)
# =====================================================================
def _email_admin_welcome(account: dict, *, to_admin: bool = True,
                         to_superadmin: bool = False) -> dict:
    """Email the ready-to-copy welcome message to the NEW ADMIN'S OWN inbox.

    FIX: the welcome mail now goes to the person it belongs to (the Admin's
    own email). Pass ``to_superadmin=True`` to ALSO copy the Super Admin.
    Previously every Admin's welcome mail was routed to the single
    SUPER_ADMIN_EMAIL inbox, so nobody received their own credentials.
    """
    subject, body = mailer.admin_welcome_email(
        account.get("full_name", ""), account.get("email", ""),
        account.get("password", ""), "Administrator")
    admin_email = (account.get("email") or "").strip()
    recipients = []
    if to_admin and admin_email:
        recipients.append(admin_email)
    if to_superadmin and config.SUPER_ADMIN_EMAIL:
        recipients.append(config.SUPER_ADMIN_EMAIL)
    if not recipients:                       # never silently send to nobody
        if admin_email:
            recipients.append(admin_email)
        elif config.SUPER_ADMIN_EMAIL:
            recipients.append(config.SUPER_ADMIN_EMAIL)
    results = [{"to": r, **mailer.send_mail(r, subject, body)} for r in recipients if r]
    return {
        "welcome_message": body,
        "subject": subject,
        "recipients": recipients,
        "results": results,
        "sent": any(r.get("sent") for r in results),
        "note": (None if recipients else
                 "No recipient email available -- copy the welcome message and send it manually"),
    }


@app.get("/api/superadmin/overview")
def superadmin_overview(user: dict = Depends(require_role("superadmin"))):
    def c(sql, params=()):
        return dbm.query_one(sql, params)["c"]
    tables = ("users", "sessions", "signatures", "messages", "security_events",
              "admin_requests", "admin_messages", "support_messages",
              "performance_metrics", "analysis_snapshots")
    return {
        "app": APP_NAME,
        "database": dbm.database_info(),
        "counts": {t: c(f"SELECT COUNT(*) c FROM {t}") for t in tables},
        "by_role": dbm.query("SELECT role, COUNT(*) c FROM users GROUP BY role"),
        "admin_requests": dbm.query(
            "SELECT status, COUNT(*) c FROM admin_requests GROUP BY status"),
        "attack_events": dbm.query(
            "SELECT event_type, severity, COUNT(*) c FROM security_events "
            "GROUP BY event_type, severity ORDER BY c DESC LIMIT 12"),
        "unauthorized_verifications": c(
            "SELECT COUNT(*) c FROM security_events "
            "WHERE event_type='UNAUTHORIZED_VERIFICATION'"),
        "urls": url_summary(),
    }


@app.get("/api/superadmin/admin-requests")
def superadmin_admin_requests(status: str = "",
                              user: dict = Depends(require_role("superadmin"))):
    if status:
        rows = dbm.query("SELECT * FROM admin_requests WHERE status=? ORDER BY id DESC",
                         (status.upper(),))
    else:
        rows = dbm.query("SELECT * FROM admin_requests ORDER BY id DESC")
    return {"requests": rows}


@app.post("/api/superadmin/admin-requests/{request_id}/approve")
async def superadmin_approve_request(request_id: str, request: Request,
                                     user: dict = Depends(require_role("superadmin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    row = dbm.query_one("SELECT * FROM admin_requests WHERE request_id=?", (request_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"Request already {row['status']}")
    password = (body.get("password") or "").strip() or None
    account = create_admin_account(
        email=row["email"], full_name=row["full_name"], password=password,
        department=row.get("department") or "Administration",
        phone=row.get("phone") or "", aadhaar=row.get("aadhaar") or "",
        department_id=row.get("department_id") or "", gender=row.get("gender") or "",
        request_id=request_id)
    mail = _email_admin_welcome(account, to_admin=True,
                                to_superadmin=bool(body.get("cc_superadmin")))
    audit.log(audit.ADMIN_CREATED, actor=user["username"], target=account["username"],
              ip=request.client.host if request.client else None,
              detail="from admin request")
    events.emit("ADMIN_APPROVED", "HIGH",
                f"Admin request {request_id} approved; account {account['username']} created",
                target=account["username"])
    return {"ok": True, "account": account, "mail": mail}


@app.post("/api/superadmin/admin-requests/{request_id}/reject")
async def superadmin_reject_request(request_id: str, request: Request,
                                    user: dict = Depends(require_role("superadmin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    row = dbm.query_one("SELECT * FROM admin_requests WHERE request_id=?", (request_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    dbm.execute("UPDATE admin_requests SET status='REJECTED', decided_at=?, "
                "decided_by=?, note=? WHERE request_id=?",
                (dbm.utcnow(), user["username"], (body.get("note") or "")[:300], request_id))
    events.emit("ADMIN_REJECTED", "MEDIUM",
                f"Admin request {request_id} rejected", target=request_id)
    return {"ok": True, "request_id": request_id, "status": "REJECTED"}


@app.get("/api/superadmin/admin-requests/pdf")
def superadmin_requests_pdf(status: str = "",
                            user: dict = Depends(require_role("superadmin"))):
    """Download admin registration details as a PDF (header = TRISHUL-Q)."""
    from . import pdf as pdfmod
    if status:
        rows = dbm.query("SELECT * FROM admin_requests WHERE status=? ORDER BY id DESC",
                         (status.upper(),))
    else:
        rows = dbm.query("SELECT * FROM admin_requests ORDER BY id DESC")
    data = pdfmod.admin_registration_pdf(rows, subtitle="Admin registration details")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition":
                             'attachment; filename="trishul-q-admin-registrations.pdf"'})


@app.get("/api/superadmin/admins")
def superadmin_admins(user: dict = Depends(require_role("superadmin"))):
    rows = dbm.query("SELECT username, full_name, email, phone, department, created_at, "
                     "last_seen, is_active FROM users WHERE role='admin' ORDER BY created_at")
    return {"admins": rows}


@app.post("/api/superadmin/admins")
async def superadmin_create_admin(request: Request,
                                  user: dict = Depends(require_role("superadmin"))):
    """Create an admin account (ID = email).

    A strong temporary password is generated (or supplied); the welcome message
    is returned and emailed to the Super Admin for review/forwarding.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    password = (body.get("password") or "").strip() or None
    account = create_admin_account(
        email=body.get("email") or "", full_name=body.get("full_name") or "",
        password=password, department=body.get("department") or "Administration",
        phone=body.get("phone") or "", created_by=user["username"])
    mail = _email_admin_welcome(account, to_admin=True,
                                to_superadmin=bool(body.get("cc_superadmin")))
    audit.log(audit.ADMIN_CREATED, actor=user["username"], target=account["username"],
              ip=request.client.host if request.client else None)
    events.emit("ADMIN_CREATED", "HIGH",
                f"Admin account {account['username']} created by Super Admin",
                target=account["username"])
    return {"ok": True, "account": account, "mail": mail}


@app.post("/api/superadmin/admins/{username}/status/{action}")
async def superadmin_admin_action(username: str, action: str, request: Request,
                                  user: dict = Depends(require_role("superadmin"))):
    username = (username or "").strip().lower()
    if action not in ("disable", "enable", "remove"):
        raise HTTPException(status_code=400, detail="action must be disable|enable|remove")
    row = dbm.query_one("SELECT * FROM users WHERE username=? AND role='admin'", (username,))
    if not row:
        raise HTTPException(status_code=404, detail="Admin not found")
    if action == "remove":
        destroy_user_sessions(username)
        dbm.execute("DELETE FROM users WHERE username=? AND role='admin'", (username,))
    else:
        dbm.execute("UPDATE users SET is_active=?, updated_at=? WHERE username=?",
                    (1 if action == "enable" else 0, dbm.utcnow(), username))
        if action == "disable":
            destroy_user_sessions(username)
    action_name = {"disable": audit.ADMIN_DEACTIVATED, "enable": audit.ADMIN_ACTIVATED,
                   "remove": audit.ADMIN_REMOVED}[action]
    audit.log(action_name, actor=user["username"], target=username,
              ip=request.client.host if request.client else None)
    events.emit(f"ADMIN_{action.upper()}", "HIGH",
                f"Super Admin {action}d admin {username}", target=username)
    return {"ok": True, "username": username, "action": action}


@app.get("/api/superadmin/users")
def superadmin_users(user: dict = Depends(require_role("superadmin"))):
    rows = dbm.query("SELECT username, role, capabilities, full_name, department, email, "
                     "device_ip, created_at, last_seen, is_active FROM users "
                     "WHERE role='user' ORDER BY created_at")
    return {"users": rows}


@app.post("/api/superadmin/users/{username}/{action}")
async def superadmin_user_action(username: str, action: str,
                                 user: dict = Depends(require_role("superadmin"))):
    username = (username or "").strip().lower()
    if action not in ("disable", "enable", "remove"):
        raise HTTPException(status_code=400, detail="action must be disable|enable|remove")
    row = dbm.query_one("SELECT * FROM users WHERE username=? AND role='user'", (username,))
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if action == "remove":
        dbm.execute("DELETE FROM sessions WHERE username=?", (username,))
        dbm.execute("DELETE FROM users WHERE username=? AND role='user'", (username,))
    else:
        dbm.execute("UPDATE users SET is_active=? WHERE username=?",
                    (1 if action == "enable" else 0, username))
        if action == "disable":
            dbm.execute("DELETE FROM sessions WHERE username=?", (username,))
    events.emit(f"USER_{action.upper()}", "MEDIUM",
                f"Super Admin {action}d user {username}", target=username)
    return {"ok": True, "username": username, "action": action}


@app.get("/api/superadmin/security-events")
def superadmin_security_events(limit: int = 200,
                               user: dict = Depends(require_role("superadmin"))):
    rows = dbm.query("SELECT * FROM security_events ORDER BY id DESC LIMIT ?",
                     (max(1, min(1000, limit)),))
    return {"events": rows}


@app.get("/api/superadmin/attack-analytics")
def superadmin_attack_analytics(user: dict = Depends(require_role("superadmin"))):
    return attack_analytics(user)


@app.post("/api/superadmin/verify-admin-data")
async def superadmin_verify_admin_data(request: Request,
                                       user: dict = Depends(require_role("superadmin"))):
    """Verify data coming from Admins: re-run independent verification on a
    message / signature and confirm its integrity on behalf of the Super Admin."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    message_id = (body.get("message_id") or "").strip()
    row = dbm.query_one("SELECT * FROM messages WHERE message_id=?", (message_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    from .qds.verification import verify_message
    sig = dbm.query_one("SELECT * FROM signatures WHERE signature_id=?", (row["signature_id"],))
    file_bytes = Path(row["file_path"]).read_bytes() if row["file_path"] else None
    verdict = verify_message(row["message"] or "", file_bytes, row["file_hash"], sig,
                             int(dbm.get_setting("n_measurements")),
                             (float(dbm.get_setting("threshold_suspicious")),
                              float(dbm.get_setting("threshold_threat"))),
                             claimed_sender=row["sender_id"],
                             actual_source_ip=row["sender_ip"])
    events.emit("SUPERADMIN_VERIFY", "INFO",
                f"Super Admin independently verified {message_id}: "
                f"{verdict['classification']}", target=message_id)
    return {"message_id": message_id, "verdict": verdict,
            "integrity_confirmed": verdict["classification"] == "LEGITIMATE"}


@app.get("/api/superadmin/messages")
def superadmin_messages(user: dict = Depends(require_role("superadmin"))):
    threads = dbm.query(
        "SELECT m.from_user AS username, u.full_name, u.department, "
        "(SELECT COUNT(*) FROM admin_messages x WHERE x.from_user=m.from_user "
        " AND x.to_user=? AND x.read_at IS NULL) AS unread, "
        "MAX(m.created_at) AS last_at FROM admin_messages m "
        "LEFT JOIN users u ON u.username = m.from_user GROUP BY m.from_user, "
        "u.full_name, u.department ORDER BY last_at DESC",
        (config.SUPERADMIN_USERNAME,))
    return {"threads": threads}


@app.get("/api/superadmin/messages/{admin_username}")
def superadmin_thread(admin_username: str, user: dict = Depends(require_role("superadmin"))):
    admin_username = (admin_username or "").strip().lower()
    rows = dbm.query("SELECT * FROM admin_messages WHERE from_user=? OR to_user=? "
                     "ORDER BY id ASC LIMIT 300", (admin_username, admin_username))
    dbm.execute("UPDATE admin_messages SET read_at=? WHERE to_user=? AND read_at IS NULL",
                (dbm.utcnow(), config.SUPERADMIN_USERNAME))
    return {"messages": rows, "username": admin_username}


@app.post("/api/superadmin/messages/reply")
async def superadmin_reply(request: Request,
                           user: dict = Depends(require_role("superadmin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    to_user = (body.get("to_user") or "").strip().lower()
    text = (body.get("body") or "").strip()[:1000]
    if not text or not to_user:
        raise HTTPException(status_code=400, detail="to_user and body are required")
    dbm.execute("INSERT INTO admin_messages(from_user, to_user, body, created_at) "
                "VALUES(?,?,?,?)", (config.SUPERADMIN_USERNAME, to_user, text, dbm.utcnow()))
    return {"ok": True, "created_at": dbm.utcnow()}


@app.get("/api/superadmin/password/generate")
def superadmin_password_generate(length: int = 14,
                                 user: dict = Depends(require_role("superadmin"))):
    from . import security
    pwd = security.generate_password(length)
    return {"password": pwd, "strength": security.password_strength(pwd)}


@app.get("/api/superadmin/mail/check")
def superadmin_mail_check(user: dict = Depends(require_role("superadmin"))):
    from . import mailer
    return mailer.check_mail()


@app.post("/api/superadmin/mail/send")
async def superadmin_mail_send(request: Request,
                               user: dict = Depends(require_role("superadmin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    to = (body.get("to") or "").strip()
    subject = (body.get("subject") or f"{APP_NAME} message").strip()
    text = (body.get("body") or "").strip()
    if not to or not text:
        raise HTTPException(status_code=400, detail="to and body are required")
    from . import mailer
    return mailer.send_mail(to, subject, text)


# =====================================================================
#  SUPER ADMIN -- admin lifecycle, audit & system status
# =====================================================================
def _reset_admin_password(username: str, actor: str, request: Request | None) -> dict:
    row = dbm.query_one("SELECT * FROM users WHERE username=? AND role='admin'", (username,))
    if not row:
        raise HTTPException(status_code=404, detail="Admin not found")
    new_pw = security.generate_password()
    dbm.execute("UPDATE users SET password_hash=?, must_change_password=1, updated_at=? "
                "WHERE username=?", (hash_password(new_pw), dbm.utcnow(), username))
    destroy_user_sessions(username)
    account = {"full_name": row.get("full_name") or username, "email": row.get("email") or username,
               "username": username, "password": new_pw}
    audit.log(audit.ADMIN_PASSWORD_RESET, actor=actor, target=username,
              ip=request.client.host if request and request.client else None)
    return account


@app.post("/api/superadmin/admins/{username}/reset-password")
async def superadmin_reset_admin_password(username: str, request: Request,
                                          user: dict = Depends(require_role("superadmin"))):
    account = _reset_admin_password(username.strip().lower(), user["username"], request)
    mail = _email_admin_welcome(account, to_admin=True, to_superadmin=False)
    return {"ok": True, "account": account, "mail": mail}


@app.post("/api/superadmin/admins/{username}/resend-welcome")
async def superadmin_resend_welcome(username: str, request: Request,
                                    user: dict = Depends(require_role("superadmin"))):
    """Generate a fresh temporary password and (re)send the welcome message.

    By default the message is sent to the Admin's OWN email address; pass
    ``{"to_superadmin": true}`` to also copy the Super Admin.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    account = _reset_admin_password(username.strip().lower(), user["username"], request)
    to_admin = body.get("to_admin", True)
    to_super = body.get("to_superadmin", False)
    if not to_admin and not to_super:
        to_super = True                      # never silently send to nobody
    mail = _email_admin_welcome(account, to_superadmin=to_super, to_admin=to_admin)
    audit.log(audit.WELCOME_EMAIL_RESENT, actor=user["username"], target=username,
              ip=request.client.host if request.client else None,
              detail=f"to_admin={to_admin} to_superadmin={to_super}")
    return {"ok": True, "account": account, "mail": mail}


@app.get("/api/superadmin/admins/{username}")
def superadmin_admin_detail(username: str, user: dict = Depends(require_role("superadmin"))):
    username = username.strip().lower()
    row = dbm.query_one(
        "SELECT username, full_name, email, phone, department, department_id, gender, "
        "role, is_active, email_verified, must_change_password, auth_provider, "
        "created_at, updated_at, last_login, last_seen, device_ip, created_by "
        "FROM users WHERE username=? AND role='admin'", (username,))
    if not row:
        raise HTTPException(status_code=404, detail="Admin not found")
    senders = dbm.query("SELECT COUNT(*) c FROM users WHERE role='user' AND owner_admin=?",
                        (username,))[0]["c"]
    return {"admin": row, "senders": senders}


@app.get("/api/superadmin/audit-logs")
def superadmin_audit_logs(limit: int = 200, action: str = "",
                          user: dict = Depends(require_role("superadmin"))):
    if action:
        return {"logs": audit.for_action(action, limit)}
    return {"logs": audit.recent(limit)}


@app.get("/api/superadmin/auth-events")
def superadmin_auth_events(limit: int = 200,
                           user: dict = Depends(require_role("superadmin"))):
    """Authentication-related audit trail (logins, failures, resets)."""
    actions = (audit.EMAIL_LOGIN, audit.GOOGLE_LOGIN, audit.FAILED_LOGIN,
               audit.SUPERADMIN_LOGIN, audit.LOGOUT, audit.PASSWORD_RESET_REQUESTED,
               audit.PASSWORD_RESET_COMPLETED, audit.PASSWORD_CHANGED)
    placeholders = ",".join("?" for _ in actions)
    rows = dbm.query(f"SELECT * FROM audit_logs WHERE action IN ({placeholders}) "
                     f"ORDER BY id DESC LIMIT ?",
                     (*actions, max(1, min(1000, limit))))
    return {"events": rows}


@app.get("/api/superadmin/system-status")
def superadmin_system_status(user: dict = Depends(require_role("superadmin"))):
    st = startup_checks.status()
    st["mail_check"] = mailer.check_mail()
    st["super_admin_email"] = config.SUPER_ADMIN_EMAIL or None
    st["public_base_url"] = config.PUBLIC_BASE_URL
    return st


# =====================================================================
#  ADMIN -- sender management (senders are managed by admins)
# =====================================================================
@app.get("/api/admin/senders")
def admin_list_senders(user: dict = Depends(require_role("admin"))):
    rows = dbm.query(
        "SELECT username, full_name, email, department, capabilities, is_active, "
        "created_at, last_seen, last_login, created_by FROM users "
        "WHERE role='user' AND owner_admin=? ORDER BY created_at", (user["username"],))
    return {"senders": rows,
            "total": len(rows), "active": sum(1 for r in rows if r.get("is_active"))}


@app.post("/api/admin/senders")
async def admin_create_sender(request: Request,
                              user: dict = Depends(require_role("admin"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    password = (body.get("password") or "").strip() or security.generate_password()
    result = create_sender(
        username=body.get("username") or "", password=password,
        full_name=body.get("full_name") or "", department=body.get("department") or "General",
        email=body.get("email") or "", phone=body.get("phone") or "",
        capability=(body.get("capability") or "send").lower(),
        owner_admin=user["username"])
    audit.log(audit.SENDER_CREATED, actor=user["username"], target=result["username"],
              ip=request.client.host if request.client else None)
    events.emit("SENDER_CREATED", "INFO",
                f"Admin {user['username']} created sender {result['username']}",
                target=result["username"])
    return {"ok": True, "sender": result, "password": password}


@app.post("/api/admin/senders/{username}/{action}")
async def admin_sender_action(username: str, action: str, request: Request,
                              user: dict = Depends(require_role("admin"))):
    username = username.strip().lower()
    if action not in ("disable", "enable", "remove"):
        raise HTTPException(status_code=400, detail="action must be disable|enable|remove")
    row = dbm.query_one("SELECT * FROM users WHERE username=? AND role='user' "
                        "AND owner_admin=?", (username, user["username"]))
    if not row:
        raise HTTPException(status_code=404, detail="Sender not found under your management")
    if action == "remove":
        destroy_user_sessions(username)
        dbm.execute("DELETE FROM users WHERE username=? AND role='user'", (username,))
    else:
        dbm.execute("UPDATE users SET is_active=?, updated_at=? WHERE username=?",
                    (1 if action == "enable" else 0, dbm.utcnow(), username))
        if action == "disable":
            destroy_user_sessions(username)
    audit.log({ "disable": audit.SENDER_DEACTIVATED, "enable": audit.SENDER_ACTIVATED,
                "remove": audit.SENDER_DEACTIVATED }[action],
              actor=user["username"], target=username,
              ip=request.client.host if request.client else None)
    return {"ok": True, "username": username, "action": action}


@app.get("/api/admin/senders/{username}")
def admin_sender_detail(username: str, user: dict = Depends(require_role("admin"))):
    username = username.strip().lower()
    row = dbm.query_one(
        "SELECT username, full_name, email, phone, department, capabilities, is_active, "
        "created_at, last_seen, last_login, device_ip, created_by FROM users "
        "WHERE username=? AND role='user' AND owner_admin=?", (username, user["username"]))
    if not row:
        raise HTTPException(status_code=404, detail="Sender not found under your management")
    sent = dbm.query("SELECT COUNT(*) c FROM messages WHERE sender_id=?", (username,))[0]["c"]
    evts = dbm.query("SELECT event_type, severity, description, timestamp FROM "
                     "security_events WHERE source=? ORDER BY id DESC LIMIT 20", (username,))
    return {"sender": row, "messages_sent": sent, "security_events": evts}


@app.get("/api/admin/dashboard")
def admin_dashboard(user: dict = Depends(require_role("admin"))):
    """Everything the Admin dashboard needs -- live values only."""
    me = user["username"]

    def c(sql, params=()):
        return dbm.query_one(sql, params)["c"]

    sender_ids = "(SELECT username FROM users WHERE owner_admin=?)"
    senders_total = c("SELECT COUNT(*) c FROM users WHERE role='user' AND owner_admin=?", (me,))
    senders_active = c("SELECT COUNT(*) c FROM users WHERE role='user' AND owner_admin=? "
                       "AND is_active=1", (me,))
    messages = c(f"SELECT COUNT(*) c FROM messages WHERE sender_id IN {sender_ids}", (me,))
    verified = c(f"SELECT COUNT(*) c FROM messages WHERE status='VERIFIED' "
                 f"AND sender_id IN {sender_ids}", (me,))
    rejected = c(f"SELECT COUNT(*) c FROM messages WHERE status='REJECTED' "
                 f"AND sender_id IN {sender_ids}", (me,))
    suspicious = c(f"SELECT COUNT(*) c FROM messages WHERE status='SUSPICIOUS' "
                   f"AND sender_id IN {sender_ids}", (me,))
    events = c("SELECT COUNT(*) c FROM security_events")
    unauth = c("SELECT COUNT(*) c FROM security_events "
               "WHERE event_type='UNAUTHORIZED_VERIFICATION'")
    recent_events = dbm.query("SELECT event_type, severity, description, timestamp "
                              "FROM security_events ORDER BY id DESC LIMIT 12")
    recent_audit = dbm.query("SELECT action, actor, target, result, created_at "
                             "FROM audit_logs ORDER BY id DESC LIMIT 12")
    return {
        "account": {"username": me, "full_name": user.get("full_name"),
                    "department": user.get("department"),
                    "is_active": user.get("is_active"),
                    "must_change_password": bool(user.get("must_change_password")),
                    "last_login": user.get("last_login")},
        "senders": {"total": senders_total, "active": senders_active,
                    "inactive": senders_total - senders_active},
        "messages": {"total": messages, "verified": verified,
                     "suspicious": suspicious, "rejected": rejected},
        "security_events": {"total": events, "unauthorized_verifications": unauth},
        "recent_events": recent_events,
        "recent_activity": recent_audit,
        "server": srv_metrics.snapshot(),
    }


# =====================================================================
#  SPA fallback -- must be LAST. Any non-API, non-asset GET returns the
#  React app so deep links (e.g. /login, /admin) survive a hard refresh.
# =====================================================================
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "assets/", "superadmin", "docs",
                             "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not found")
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({
        "app": APP_NAME, "version": VERSION,
        "note": "React frontend not built yet. Run `npm install && npm run build` "
                "inside frontend/, or use the API at /docs.",
        "superadmin": "/superadmin",
    })
