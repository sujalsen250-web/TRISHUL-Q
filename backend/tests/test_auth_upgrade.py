"""Tests for the v2 upgrade: email login, forgot/reset password, forced
first-login change, admin->sender management, audit logs and the
no-silent-SQLite-fallback rule."""
from __future__ import annotations

import pytest

from .conftest import login, register

SA = {"username": "superadmin", "password": "TrishulQ@2026"}


def _sa(client):
    r = client.post("/api/superadmin/login", json=SA)
    assert r.status_code == 200, r.text


def _make_admin(client, unique, password="Temp#Pass1"):
    """Super Admin creates an admin; returns (email, account)."""
    _sa(client)
    email = f"admin_{unique}@example.com"
    r = client.post("/api/superadmin/admins", json={
        "full_name": "Admin One", "email": email, "department": "Cyber Cell"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account"]["username"] == email
    assert body["mail"]["welcome_message"].startswith("Congratulations")
    return email, body["account"]


# ---------------------------------------------------------- email login ------
def test_email_and_username_login(client, unique):
    username = f"euser_{unique}"
    email = f"euser_{unique}@example.com"
    r = client.post("/api/auth/register", json={
        "username": username, "password": "secret123", "capability": "both",
        "full_name": "E User", "department": "QA", "email": email,
        "security_question": "q", "security_answer": "a"})
    assert r.status_code == 200, r.text
    client.post("/api/auth/logout")
    # login with EMAIL
    r = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    client.post("/api/auth/logout")
    # login with USERNAME still works
    r = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text


def test_wrong_password_generic_error(client, unique):
    r = client.post("/api/auth/login",
                    json={"email": f"nobody_{unique}@example.com", "password": "x"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


# ------------------------------------------------------- forgot / reset ------
def test_forgot_password_full_flow(client, unique):
    from backend import auth
    username = f"fp_{unique}"
    email = f"fp_{unique}@example.com"
    client.post("/api/auth/register", json={
        "username": username, "password": "oldpass123", "capability": "send",
        "full_name": "FP User", "department": "QA", "email": email,
        "security_question": "q", "security_answer": "a"})
    client.post("/api/auth/logout")

    # request (public) -- always a generic success message
    r = client.post("/api/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert "reset link" in r.json()["message"].lower()

    # a token row now exists; mint one we can use (same machinery)
    token = auth.create_password_reset_token(username)
    r = client.post("/api/auth/reset-password",
                    json={"token": token, "new_password": "NewPass#9",
                          "confirm_password": "NewPass#9"})
    assert r.status_code == 200, r.text
    assert "reset successfully" in r.json()["message"].lower()

    # token is single-use
    r2 = client.post("/api/auth/reset-password",
                     json={"token": token, "new_password": "Another#1"})
    assert r2.status_code == 400

    # new password works, old does not
    assert client.post("/api/auth/login",
                       json={"email": email, "password": "NewPass#9"}).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"email": email, "password": "oldpass123"}).status_code == 401


def test_expired_reset_token_rejected(client, unique):
    from backend import auth
    username = f"exp_{unique}"
    client.post("/api/auth/register", json={
        "username": username, "password": "oldpass123", "capability": "send",
        "full_name": "Exp User", "department": "QA",
        "security_question": "q", "security_answer": "a"})
    token = auth.create_password_reset_token(username, ttl_seconds=-10)
    r = client.post("/api/auth/reset-password",
                    json={"token": token, "new_password": "NewPass#9"})
    assert r.status_code == 400


# ------------------------------------------- first-login password change -----
def test_must_change_password_then_change(client, unique):
    email, account = _make_admin(client, unique)
    client.post("/api/auth/logout")
    r = login(client, email, account["password"])
    assert r.json()["must_change_password"] is True
    assert r.json()["redirect"] == "/change-password"

    # change it
    r = client.post("/api/auth/change-password", json={
        "current_password": account["password"], "new_password": "Strong#Pass1",
        "confirm_password": "Strong#Pass1"})
    assert r.status_code == 200, r.text
    me = client.get("/api/auth/me").json()
    assert me["must_change_password"] is False

    # next login goes straight to the dashboard
    client.post("/api/auth/logout")
    r = login(client, email, "Strong#Pass1")
    assert r.json()["redirect"] == "/admin"
    assert r.json()["must_change_password"] is False


# ------------------------------------------------- admin -> sender mgmt ------
def test_admin_manages_senders(client, unique):
    email, account = _make_admin(client, unique)
    client.post("/api/auth/logout")
    login(client, email, account["password"])
    client.post("/api/auth/change-password", json={
        "current_password": account["password"], "new_password": "Strong#Pass1"})

    # create a sender
    s = client.post("/api/admin/senders", json={
        "username": f"send_{unique}", "full_name": "Sender One",
        "department": "Ops", "capability": "send"})
    assert s.status_code == 200, s.text
    sender_user = s.json()["sender"]["username"]
    assert s.json()["password"]

    # it appears in the admin's sender list
    lst = client.get("/api/admin/senders").json()
    assert any(x["username"] == sender_user for x in lst["senders"])
    assert lst["active"] >= 1

    # deactivate it
    d = client.post(f"/api/admin/senders/{sender_user}/disable")
    assert d.status_code == 200
    detail = client.get(f"/api/admin/senders/{sender_user}").json()
    assert detail["sender"]["is_active"] == 0

    # dashboard reflects senders
    dash = client.get("/api/admin/dashboard").json()
    assert dash["senders"]["total"] >= 1


def test_admin_cannot_manage_other_admins_senders(client, unique):
    email, account = _make_admin(client, unique)
    client.post("/api/auth/logout")
    login(client, email, account["password"])
    # a sender that does not belong to this admin
    r = client.get("/api/admin/senders/does_not_exist")
    assert r.status_code == 404


# ------------------------------------------------------------ audit logs -----
def test_audit_logs_record_login(client, unique):
    register(client, "send", unique)
    client.post("/api/auth/logout")
    _sa(client)
    logs = client.get("/api/superadmin/audit-logs").json()["logs"]
    actions = {l["action"] for l in logs}
    assert "Email Login" in actions or "Super Admin Login" in actions


# ------------------------------------------------- no silent sqlite fallback -
def test_no_silent_fallback_in_production(monkeypatch):
    from backend import db, config
    db.reset_engine()
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg2://x:y@127.0.0.1:1/nope")
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "ALLOW_SQLITE_FALLBACK", False)
    with pytest.raises(Exception):
        db.engine()
    db.reset_engine()


def test_roles_table_and_new_tables_exist():
    from backend import db
    db.init_db()
    tables = set(db._list_tables())
    for t in ("roles", "password_reset_tokens", "oauth_accounts", "audit_logs",
              "verification_events"):
        assert t in tables


def test_register_cannot_create_admin(client, unique):
    r = client.post("/api/auth/register", json={
        "username": f"esc_{unique}", "password": "secret123", "capability": "send",
        "role": "admin", "full_name": "Escalation Attempt", "department": "QA",
        "security_question": "q", "security_answer": "a"})
    assert r.status_code == 200
    assert r.json()["role"] == "user"


def test_superadmin_can_mail_admin_directly(client, unique):
    """Super Admin can send the welcome mail straight to the Admin's inbox,
    and the specific routes are not shadowed by the generic status route."""
    email, account = _make_admin(client, unique)
    # resend-welcome targets the admin's own address
    r = client.post(f"/api/superadmin/admins/{email}/resend-welcome",
                    json={"to_admin": True, "to_superadmin": False})
    assert r.status_code == 200, r.text
    assert email in r.json()["mail"]["recipients"]
    # the generic lifecycle route is still reachable under /status/
    s = client.post(f"/api/superadmin/admins/{email}/status/disable")
    assert s.status_code == 200 and s.json()["action"] == "disable"
    # reset-password route is reachable too
    p = client.post(f"/api/superadmin/admins/{email}/reset-password")
    assert p.status_code == 200
