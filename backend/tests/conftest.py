"""Shared pytest fixtures for the TRISHUL-Q test-suite.

Tests run against a temporary SQLite database (PostgreSQL is the production
store, but the suite must run anywhere). The persistence layer is exercised
through the same helpers the app uses, so the SQL dialect coverage is real.
"""
from __future__ import annotations

import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="trishulq-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["TRISHUL_DB_FALLBACK"] = "1"
os.environ["TRISHUL_SEED_DEFAULT_ADMIN"] = "1"
os.environ["TRISHUL_DATA_DIR"] = _TMP

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def unique() -> str:
    return uuid.uuid4().hex[:8]


def register(client, cap: str, unique: str, password: str = "secret123") -> str:
    username = f"u_{cap}_{unique}"
    r = client.post("/api/auth/register", json={
        "username": username, "password": password, "capability": cap,
        "full_name": f"Test {cap} {unique}", "department": "QA",
        "security_question": "q", "security_answer": "a"})
    assert r.status_code == 200, r.text
    return username


def login(client, username: str, password: str = "secret123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r
