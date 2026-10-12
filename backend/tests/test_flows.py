"""End-to-end flow tests: registration, admin-request/approval, Super Admin
isolation, QDS send/verify and the UNAUTHORIZED_VERIFICATION event."""
from __future__ import annotations

from .conftest import login, register

SA = {"username": "superadmin", "password": "TrishulQ@2026"}


def _superadmin_login(client):
    r = client.post("/api/superadmin/login", json=SA)
    assert r.status_code == 200, r.text
    return r


def test_superadmin_isolation_blocks_non_local_host(client):
    # a request with a public Host header is rejected before any route logic
    r = client.get("/api/superadmin/overview", headers={"host": "evil.example.com"})
    assert r.status_code == 403
    r2 = client.get("/superadmin", headers={"host": "evil.example.com"})
    assert r2.status_code == 403


def test_superadmin_can_login_locally(client):
    _superadmin_login(client)
    r = client.get("/api/superadmin/overview")
    assert r.status_code == 200
    assert r.json()["app"] == "TRISHUL-Q"


def test_superadmin_requires_authentication(client):
    client.post("/api/auth/logout")
    r = client.get("/api/superadmin/admins")
    assert r.status_code == 401


def test_admin_request_and_approval_flow(client, unique):
    email = f"admin_{unique}@example.com"
    r = client.post("/api/admin-requests", json={
        "full_name": "Asha Rao", "email": email, "phone": "9999999999",
        "aadhaar": "1234-5678-9012", "department_id": "DEPT-1",
        "department": "Cyber Cell", "gender": "F"})
    assert r.status_code == 200, r.text
    request_id = r.json()["request_id"]

    # status lookup is public
    st = client.get(f"/api/admin-requests/status?request_id={request_id}")
    assert st.status_code == 200 and st.json()["status"] == "PENDING"

    _superadmin_login(client)
    pend = client.get("/api/superadmin/admin-requests?status=PENDING").json()["requests"]
    assert any(x["request_id"] == request_id for x in pend)

    appr = client.post(f"/api/superadmin/admin-requests/{request_id}/approve",
                       json={"email": False})
    assert appr.status_code == 200, appr.text
    account = appr.json()["account"]
    assert account["username"] == email

    # the new admin can sign in on the public app
    client.post("/api/auth/logout")
    r = login(client, email, account["password"])
    assert r.json()["role"] == "admin"
    # a generated password forces a first-login change
    assert r.json()["must_change_password"] is True
    assert r.json()["redirect"] == "/change-password"


def test_superadmin_password_generator(client):
    _superadmin_login(client)
    r = client.get("/api/superadmin/password/generate?length=16")
    assert r.status_code == 200
    pwd = r.json()["password"]
    assert len(pwd) >= 16
    assert any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd)


def test_superadmin_pdf_export(client):
    _superadmin_login(client)
    r = client.get("/api/superadmin/admin-requests/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_qds_send_verify_and_unauthorized_event(client, unique):
    sender = register(client, "send", unique)
    receiver = register(client, "receive", unique)
    intruder = register(client, "receive", unique + "x")

    # ---- sender generates a signature ----
    login(client, sender)
    message = "TRISHUL-Q integrity test message"
    gen = client.post("/api/signature/generate", json={"message": message})
    assert gen.status_code == 200, gen.text
    sig = gen.json()
    assert sig["pauli_basis_counts"]  # v8 Pauli key committed
    assert "pauli_key_preview" in sig

    # ---- sender sends it ----
    send = client.post("/api/send", data={
        "message": message, "signature_id": sig["signature_id"],
        "nonce": sig["nonce"], "receiver_username": receiver})
    assert send.status_code == 200, send.text
    body = send.json()
    assert body["verdict"]["action"] == "ACCEPT", body["verdict"]["reasons"]
    assert body["verdict"]["pauli_verification"]["passed"] is True
    message_id = body["message_id"]

    # ---- receiver can read it ----
    login(client, receiver)
    got = client.get(f"/api/messages/{message_id}")
    assert got.status_code == 200
    assert got.json()["verdict"]["pauli_verification"]["checked"] >= 1

    # ---- an unrelated user triggers a first-class security event ----
    login(client, intruder)
    bad = client.get(f"/api/messages/{message_id}")
    assert bad.status_code == 403
    client.post("/api/auth/logout")
    _superadmin_login(client)
    evts = client.get("/api/superadmin/security-events?limit=200").json()["events"]
    assert any(e["event_type"] == "UNAUTHORIZED_VERIFICATION" for e in evts)


def test_admin_security_analysis_live(client, unique):
    _superadmin_login(client)
    # promote a fresh admin through the request flow
    email = f"analyst_{unique}@example.com"
    req = client.post("/api/admin-requests", json={"full_name": "Analyst",
                                                   "email": email}).json()
    acc = client.post(f"/api/superadmin/admin-requests/{req['request_id']}/approve",
                      json={"email": False}).json()["account"]
    client.post("/api/auth/logout")
    login(client, email, acc["password"])
    r = client.get("/api/security/analysis?n_qubits=48&trials=40")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["checks"] >= 1
    assert 0.0 <= data["p_forge_closed_form"] <= 1.0
    assert "suite" in data and "p_forge_vs_n_qubits" in data
